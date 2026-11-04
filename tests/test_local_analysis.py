"""Local scans exercise the real CLI, report assembly, and Dockerfile scanner."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from repo_analyzer.cli import cli
from repo_analyzer.repository_analyzer import RepositoryAnalyzer


class TestLocalAnalysis(unittest.TestCase):
    def _patch(self, *args, **kwargs):
        patcher = patch(*args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checkout = self.root / 'customer checkout'
        self.checkout.mkdir()
        (self.checkout / 'Dockerfile').write_text('FROM cgr.dev/chainguard/python:latest\n')
        (self.checkout / 'uncommitted.txt').write_text('preserve me\n')
        self.report = self.root / 'reports' / 'analysis.json'
        for target in ('repo_analyzer.cli.load_dotenv',
                       'repo_analyzer.repository_analyzer.get_analyzer',
                       'repo_analyzer.repository_analyzer.GitCloner'):
            mock = self._patch(target)
            if not target.endswith('load_dotenv'):
                mock.side_effect = AssertionError('Local scans must not access remote repositories')
        self._patch('repo_analyzer.repository_analyzer.SyftAnalyzer.check_syft_available', return_value=True)
        self.syft = self._patch(
            'repo_analyzer.repository_analyzer.SyftAnalyzer.analyze_repository',
            return_value={'artifacts': [{'name': 'requests', 'version': '2.32.5',
                                        'type': 'python', 'locations': [{'path': 'requirements.txt'}]}]},
        )
        env_patch = patch.dict(os.environ, {}, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def invoke(self, *extra):
        return CliRunner().invoke(cli, ['-p', 'local', '-s', str(self.checkout),
                                        '-O', str(self.report), *extra])

    def test_scan_without_credentials_preserves_checkout_and_writes_report(self):
        before = {p.name: p.read_bytes() for p in self.checkout.iterdir()}
        result = self.invoke('-v')
        self.assertEqual(result.exit_code, 0, result.output)
        data = json.loads(self.report.read_text())
        self.assertEqual(data['platform'], 'local')
        self.assertEqual(data['analyzed_projects'], 1)
        self.assertEqual(data['total_dependencies'], 1)
        self.assertEqual(data['ecosystems_breakdown']['python']['total_dependencies'], 1)
        project = data['projects'][0]
        self.assertEqual(project['repository']['url'], self.checkout.resolve().as_uri())
        self.assertEqual(project['dockerfile_adoption']['dockerfiles_found'], 1)
        self.syft.assert_called_once_with(str(self.checkout.resolve()))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.checkout.iterdir()})

    def test_remote_environment_does_not_enable_authentication(self):
        with patch.dict(os.environ, {'PLATFORM': 'github', 'TOKEN': 'unused', 'ORG': 'unused'}):
            result = self.invoke()
        self.assertEqual(result.exit_code, 0, result.output)

    def test_missing_directory_is_rejected(self):
        self.checkout = self.root / 'missing'
        result = self.invoke()
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('does not exist', result.output)
        self.syft.assert_not_called()
        self.assertFalse(self.report.exists())

    def test_file_source_is_rejected(self):
        self.checkout = self.checkout / 'Dockerfile'
        result = self.invoke()
        self.assertNotEqual(result.exit_code, 0)
        self.syft.assert_not_called()

    def test_remote_selectors_are_rejected(self):
        for option in ('--branch', '--repo'):
            result = self.invoke(option, 'main')
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn('current checkout', result.output)
        self.syft.assert_not_called()

    def test_syft_failure_exits_without_report(self):
        self.syft.return_value = None
        result = self.invoke()
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('Syft analysis failed', result.output)
        self.assertFalse(self.report.exists())

    def test_dockerfile_only_checkout(self):
        self.syft.return_value = {'artifacts': []}
        analysis = RepositoryAnalyzer('local').analyze_local(str(self.checkout))
        self.assertEqual(analysis.analyzed_projects, 1)
        self.assertEqual(analysis.total_dependencies, 0)

    def test_empty_directory_is_reported_as_skipped(self):
        empty = self.root / 'empty'
        empty.mkdir()
        self.syft.return_value = {'artifacts': []}
        analysis = RepositoryAnalyzer('local').analyze_local(str(empty))
        self.assertEqual(analysis.analyzed_projects, 0)
        self.assertEqual(len(analysis.skipped_projects), 1)
        self.assertTrue(empty.is_dir())
