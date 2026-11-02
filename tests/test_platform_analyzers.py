"""Tests for platform analyzer factory, auth, timeouts, and pagination."""

import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from repo_analyzer.platform_analyzers import get_analyzer, PlatformAnalyzer
from repo_analyzer.github_analyzer import GitHubAnalyzer
from repo_analyzer.gitlab_analyzer import GitLabAnalyzer
from repo_analyzer.azure_devops_analyzer import AzureDevOpsAnalyzer
from repo_analyzer.models import RepositoryInfo


class TestFactory(unittest.TestCase):

    def test_github(self):
        self.assertIsInstance(get_analyzer('github', 'https://github.com', 't'), GitHubAnalyzer)

    def test_gitlab(self):
        self.assertIsInstance(get_analyzer('gitlab', 'https://gitlab.com', 't'), GitLabAnalyzer)

    def test_ado(self):
        self.assertIsInstance(get_analyzer('ado', 'https://dev.azure.com/org', 't'), AzureDevOpsAnalyzer)

    def test_invalid_platform(self):
        with self.assertRaises(ValueError):
            get_analyzer('bitbucket', 'https://x', 't')


class TestAuthHeaders(unittest.TestCase):

    def test_github_header(self):
        a = GitHubAnalyzer('https://github.com', 'tok')
        self.assertEqual(a.session.headers['Authorization'], 'token tok')

    def test_gitlab_header(self):
        a = GitLabAnalyzer('https://gitlab.com', 'tok')
        self.assertEqual(a.session.headers['Authorization'], 'Bearer tok')

    def test_ado_header(self):
        a = AzureDevOpsAnalyzer('https://dev.azure.com/org', 'tok')
        self.assertTrue(a.session.headers['Authorization'].startswith('Basic '))


class TestTimeout(unittest.TestCase):

    def test_default_timeout(self):
        a = GitHubAnalyzer('https://github.com', 't')
        self.assertEqual(a.timeout, 60)

    @patch.dict(os.environ, {'REQUEST_TIMEOUT': '120'})
    def test_env_override(self):
        a = GitHubAnalyzer('https://github.com', 't')
        self.assertEqual(a.timeout, 120)


class TestAdoPaginationAuthFailure(unittest.TestCase):
    """401/403 must propagate — auth errors are not transient."""

    def test_403_reraises(self):
        a = AzureDevOpsAnalyzer('https://dev.azure.com/org', 'tok')
        response = MagicMock()
        response.status_code = 403
        http_err = requests.exceptions.HTTPError(response=response)
        response.raise_for_status.side_effect = http_err
        with patch.object(a.session, 'get', return_value=response):
            with self.assertRaises(requests.exceptions.HTTPError):
                a._make_paginated_request('https://dev.azure.com/org/_apis/projects')

    def test_500_swallowed(self):
        a = AzureDevOpsAnalyzer('https://dev.azure.com/org', 'tok')
        response = MagicMock()
        response.status_code = 500
        http_err = requests.exceptions.HTTPError(response=response)
        response.raise_for_status.side_effect = http_err
        with patch.object(a.session, 'get', return_value=response):
            self.assertEqual(a._make_paginated_request('https://x'), [])


class TestAdoSubdomainUrl(unittest.TestCase):

    def test_vssps_subdomain(self):
        a = AzureDevOpsAnalyzer('https://dev.azure.com', 'tok')
        url = a._generate_request_url('_apis/graph/users', 'myorg', sub_api='vssps')
        self.assertEqual(url, 'https://vssps.dev.azure.com/myorg/_apis/graph/users')

    def test_non_azure_host_unchanged(self):
        a = AzureDevOpsAnalyzer('https://ado.corp.example', 'tok')
        url = a._generate_request_url('_apis/graph/users', 'myorg', sub_api='vssps')
        self.assertEqual(url, 'https://ado.corp.example/myorg/_apis/graph/users')


if __name__ == '__main__':
    unittest.main()
