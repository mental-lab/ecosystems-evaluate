"""Tests for GitCloner authentication and token handling."""

import base64
import os
import unittest

from repo_analyzer.git_cloner import GitCloner


class TestAuthHeader(unittest.TestCase):
    """Verify the Authorization header scheme per platform."""

    def test_github_uses_basic(self):
        # GitHub's git endpoints do not accept Bearer — fine-grained PATs
        # included; Basic with x-access-token is required
        cloner = GitCloner(token='tok123', platform='github')
        expected = base64.b64encode(b'x-access-token:tok123').decode()
        self.assertEqual(cloner._get_auth_header(), f'Authorization: Basic {expected}')

    def test_gitlab_uses_bearer(self):
        cloner = GitCloner(token='tok123', platform='gitlab')
        self.assertEqual(cloner._get_auth_header(), 'Authorization: Bearer tok123')

    def test_ado_uses_basic(self):
        cloner = GitCloner(token='tok123', platform='ado')
        expected = base64.b64encode(b':tok123').decode()
        self.assertEqual(cloner._get_auth_header(), f'Authorization: Basic {expected}')

    def test_no_token_no_header(self):
        cloner = GitCloner(token=None, platform='github')
        self.assertIsNone(cloner._get_auth_header())


class TestAuthEnv(unittest.TestCase):
    """Verify the token reaches git via env, never via the command line."""

    def test_token_in_env_not_argv(self):
        cloner = GitCloner(token='secret-tok', platform='gitlab')
        env = cloner._build_auth_env()
        self.assertEqual(env['GIT_CONFIG_COUNT'], '1')
        self.assertEqual(env['GIT_CONFIG_KEY_0'], 'http.extraHeader')
        self.assertIn('Bearer secret-tok', env['GIT_CONFIG_VALUE_0'])

    def test_no_token_leaves_env_untouched(self):
        cloner = GitCloner(token=None, platform='github')
        env = cloner._build_auth_env()
        self.assertNotIn('GIT_CONFIG_COUNT', env)


class TestRedaction(unittest.TestCase):
    """The token must never appear in logged output."""

    def test_redact_token(self):
        cloner = GitCloner(token='secret-tok', platform='github')
        text = 'fatal: unable to access https://secret-tok@github.com/x/y'
        self.assertEqual(cloner._redact(text), 'fatal: unable to access https://***@github.com/x/y')

    def test_redact_without_token_passthrough(self):
        cloner = GitCloner(token=None, platform='github')
        self.assertEqual(cloner._redact('some error'), 'some error')


if __name__ == '__main__':
    unittest.main()
