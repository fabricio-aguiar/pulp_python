"""Tests that publish file plugin repositories."""
import unittest
from random import choice

from pulp_smash import config
from pulp_smash.pulp3.bindings import monitor_task
from pulp_smash.pulp3.utils import (
    gen_repo,
    get_content,
    gen_distribution,
    get_versions,
)

from pulp_python.tests.functional.constants import PYTHON_CONTENT_NAME
from pulp_python.tests.functional.utils import (
    gen_python_client,
    gen_python_remote,
)
from pulp_python.tests.functional.utils import set_up_module as setUpModule  # noqa:F401

from pulpcore.client.pulp_python import (
    DistributionsPypiApi,
    PublicationsPypiApi,
    RepositoriesPythonApi,
    RepositoryAddRemoveContent,
    RepositorySyncURL,
    RemotesPythonApi,
    PythonPythonPublication,
)
from pulpcore.client.pulp_python.exceptions import ApiException


class PublishAnyRepoVersionTestCase(unittest.TestCase):
    """Test whether a particular repository version can be published.

    This test targets the following issues:

    * `Pulp #3324 <https://pulp.plan.io/issues/3324>`_
    * `Pulp Smash #897 <https://github.com/pulp/pulp-smash/issues/897>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()

        client = gen_python_client()
        cls.repo_api = RepositoriesPythonApi(client)
        cls.remote_api = RemotesPythonApi(client)
        cls.publications = PublicationsPypiApi(client)
        cls.distributions = DistributionsPypiApi(client)

    def setUp(self):
        """Create a new repository before each test."""
        pypi_path = "/pulp/content/pulp_pre_upgrade_test"
        url = self.cfg.get_content_host_base_url() + pypi_path
        body = gen_python_remote(url=url)
        remote = self.remote_api.create(body)

        repo = self.repo_api.create(gen_repo())

        repository_sync_data = RepositorySyncURL(remote=remote.pulp_href)
        sync_response = self.repo_api.sync(repo.pulp_href, repository_sync_data)
        monitor_task(sync_response.task)

        self.repo = self.repo_api.read(repo.pulp_href)

    def test_all(self):
        """Test whether a particular repository version can be published.

        1. Create a repository with at least 2 repository versions.
        2. Create a publication by supplying the latest ``repository_version``.
        3. Assert that the publication ``repository_version`` attribute points
           to the latest repository version.
        4. Create a publication by supplying the non-latest ``repository_version``.
        5. Create distribution.
        6. Assert that the publication ``repository_version`` attribute points
           to the supplied repository version.
        7. Assert that an exception is raised when providing two different
           repository versions to be published at same time.
        """
        # Step 1
        repo_content = get_content(self.repo.to_dict())[PYTHON_CONTENT_NAME]
        print(repo_content)
        for file_content in repo_content:
            repository_modify_data = RepositoryAddRemoveContent(
                remove_content_units=[file_content["pulp_href"]]
            )
            modify_response = self.repo_api.modify(self.repo.pulp_href, repository_modify_data)
            monitor_task(modify_response.task)
        version_hrefs = tuple(ver["pulp_href"] for ver in get_versions(self.repo.to_dict()))
        print(version_hrefs)
        non_latest = choice(version_hrefs[:-1])

        # Step 2
        publish_data = PythonPythonPublication(repository=self.repo.pulp_href)
        publication = self.create_publication(publish_data)

        # Step 3
        self.assertEqual(publication.repository_version, version_hrefs[-1])

        # Step 4
        publish_data = PythonPythonPublication(repository_version=non_latest)
        publication = self.create_publication(publish_data)

        # Step 5
        body = gen_distribution()
        body["base_path"] = "pulp_post_upgrade_test"
        body["publication"] = publication.pulp_href

        distribution_response = self.distributions.create(body)
        created_resources = monitor_task(distribution_response.task).created_resources
        distribution = self.distributions.read(created_resources[0])

        # Step 6
        self.assertEqual(publication.repository_version, non_latest)

        # Step 7
        with self.assertRaises(ApiException):
            body = {"repository": self.repo.pulp_href, "repository_version": non_latest}
            self.publications.create(body)

        # Step 8
        url = self.cfg.get_content_host_base_url() + "/pypi/pulp_post_upgrade_test/"
        self.assertEqual(url, distribution.base_url, url)

    def create_publication(self, publish_data):
        """Create a new publication from the passed data."""
        publish_response = self.publications.create(publish_data)
        created_resources = monitor_task(publish_response.task).created_resources
        publication_href = created_resources[0]
        return self.publications.read(publication_href)
