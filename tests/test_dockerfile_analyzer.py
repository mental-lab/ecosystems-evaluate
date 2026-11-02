"""Tests for DockerfileAnalyzer base image extraction and Chainguard detection."""

import tempfile
import unittest
from pathlib import Path

from repo_analyzer.dockerfile_analyzer import DockerfileAnalyzer


class TestDockerfileAnalyzer(unittest.TestCase):

    def setUp(self):
        self.analyzer = DockerfileAnalyzer()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, rel_path, content):
        path = self.repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_no_dockerfiles(self):
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertEqual(results['dockerfiles_found'], 0)
        self.assertFalse(results['adoption_detected'])

    def test_detects_chainguard_image(self):
        self._write('Dockerfile', 'FROM cgr.dev/chainguard/python:latest\nRUN echo hi\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertEqual(results['dockerfiles_found'], 1)
        self.assertTrue(results['adoption_detected'])
        self.assertIn('cgr.dev/chainguard/python:latest', results['chainguard_images'])

    def test_detects_other_image(self):
        self._write('Dockerfile', 'FROM ubuntu:22.04\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertFalse(results['adoption_detected'])
        self.assertIn('ubuntu:22.04', results['other_images'])

    def test_multistage_and_platform_flag(self):
        self._write('Dockerfile',
                    'FROM --platform=linux/amd64 cgr.dev/chainguard/go:latest-dev AS build\n'
                    'FROM scratch\n'
                    'COPY --from=build /app /app\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        # scratch is skipped; the chainguard base is detected
        self.assertTrue(results['adoption_detected'])
        self.assertEqual(results['other_images'], [])

    def test_finds_nested_dockerfile_variants(self):
        self._write('services/api/Dockerfile.prod', 'FROM cgr.dev/chainguard/node:latest\n')
        self._write('services/worker/worker.dockerfile', 'FROM ubuntu:22.04\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertEqual(results['dockerfiles_found'], 2)


if __name__ == '__main__':
    unittest.main()
