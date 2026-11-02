"""CLI tests for argument validation, .env loading, env fallbacks, and errors."""

import logging
import os
import unittest
from unittest.mock import MagicMock, patch

import requests
from click.testing import CliRunner

from main import cli  # via the backwards-compat shim; real home is repo_analyzer.cli


class TestCli(unittest.TestCase):

    ENV_KEYS = ('PLATFORM', 'SOURCE', 'TOKEN', 'ORG', 'WORKERS')

    def setUp(self):
        self.runner = CliRunner()
        # load_dotenv mutates os.environ — save and restore so .env values
        # loaded inside the CLI don't leak between tests
        self._saved_env = {k: os.environ.get(k) for k in self.ENV_KEYS}

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_help(self):
        result = self.runner.invoke(cli, ['--help'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn('--platform', result.output)

    def test_missing_required_args(self):
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['-O', 'out.json'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('required', result.output)

    def test_token_flag_warns(self):
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, [
                '-p', 'github', '-s', 'https://github.com',
                '-t', 'tok', '-o', 'org', '-O', 'out.json'
            ])
        self.assertIn('shell history', result.output)

    def test_env_vars_satisfy_required_args(self):
        """PLATFORM/SOURCE/TOKEN/ORG env vars should pass validation."""
        env = {'PLATFORM': 'github', 'SOURCE': 'https://github.com',
               'TOKEN': 'tok', 'ORG': 'org'}
        with self.runner.isolated_filesystem():
            with patch('repo_analyzer.cli.RepositoryAnalyzer') as mock_ra:
                mock_ra.side_effect = RuntimeError('sentinel')
                result = self.runner.invoke(cli, ['-O', 'out.json'], env=env)
        # Got past validation and reached analyzer construction
        self.assertIn('sentinel', result.output)

    def test_dotenv_file_loaded(self):
        """Values in a .env file should be picked up automatically."""
        with self.runner.isolated_filesystem() as td:
            with open('.env', 'w') as f:
                f.write('PLATFORM=github\nSOURCE=https://github.com\n'
                        'TOKEN=tok\nORG=org\n')
            with patch('repo_analyzer.cli.RepositoryAnalyzer') as mock_ra:
                mock_ra.side_effect = RuntimeError('sentinel')
                result = self.runner.invoke(cli, ['-O', 'out.json'])
        self.assertIn('sentinel', result.output)

    def test_workers_env_var_honored(self):
        """WORKERS env var should be used when -w is not passed."""
        env = {'PLATFORM': 'github', 'SOURCE': 'https://github.com',
               'TOKEN': 'tok', 'ORG': 'org', 'WORKERS': '9'}
        with self.runner.isolated_filesystem():
            with patch('repo_analyzer.cli.RepositoryAnalyzer') as mock_ra:
                mock_ra.side_effect = RuntimeError('sentinel')
                result = self.runner.invoke(cli, ['-O', 'out.json'], env=env)
        self.assertIn('sentinel', result.output)
        self.assertEqual(mock_ra.call_args.kwargs['max_workers'], 9)

    def test_workers_flag_overrides_env(self):
        env = {'PLATFORM': 'github', 'SOURCE': 'https://github.com',
               'TOKEN': 'tok', 'ORG': 'org', 'WORKERS': '9'}
        with self.runner.isolated_filesystem():
            with patch('repo_analyzer.cli.RepositoryAnalyzer') as mock_ra:
                mock_ra.side_effect = RuntimeError('sentinel')
                result = self.runner.invoke(cli, ['-O', 'out.json', '-w', '2'], env=env)
        self.assertEqual(mock_ra.call_args.kwargs['max_workers'], 2)

    def test_workers_rejects_zero(self):
        env = {'PLATFORM': 'github', 'SOURCE': 'https://github.com',
               'TOKEN': 'tok', 'ORG': 'org'}
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['-O', 'out.json', '-w', '0'], env=env)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('at least 1', result.output)

    def test_verbose_configures_info_logging(self):
        with self.runner.isolated_filesystem():
            with patch.object(logging, 'basicConfig') as mock_bc:
                self.runner.invoke(cli, ['-O', 'out.json', '-v'])
        self.assertEqual(mock_bc.call_args.kwargs['level'], logging.INFO)

    def test_default_configures_warning_logging(self):
        with self.runner.isolated_filesystem():
            with patch.object(logging, 'basicConfig') as mock_bc:
                self.runner.invoke(cli, ['-O', 'out.json'])
        self.assertEqual(mock_bc.call_args.kwargs['level'], logging.WARNING)

    def test_http_401_shows_friendly_hint(self):
        """Auth failures should explain what to check, not just dump the error."""
        env = {'PLATFORM': 'github', 'SOURCE': 'https://github.com',
               'TOKEN': 'tok', 'ORG': 'org'}
        response = MagicMock()
        response.status_code = 401
        http_err = requests.exceptions.HTTPError('401 Client Error', response=response)
        with self.runner.isolated_filesystem():
            with patch('repo_analyzer.cli.RepositoryAnalyzer') as mock_ra:
                mock_ra.return_value.analyze_organization.side_effect = http_err
                result = self.runner.invoke(cli, ['-O', 'out.json'], env=env)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('TOKEN', result.output)


if __name__ == '__main__':
    unittest.main()
