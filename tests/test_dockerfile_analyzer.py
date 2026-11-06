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

    def test_excludes_chained_stage_aliases(self):
        self._write('Dockerfile',
                    'FROM cgr.dev/chainguard/go:latest-dev AS builder\n'
                    'FROM builder AS test\n'
                    'FROM test AS release\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertEqual(results['chainguard_images'], ['cgr.dev/chainguard/go:latest-dev'])
        self.assertEqual(results['other_images'], [])
        self.assertEqual(results['dockerfiles'][0]['other_images'], [])

    def test_stage_aliases_with_platform_and_mixed_case(self):
        self._write('Dockerfile',
                    'from golang:1.24 as Build\n'
                    'FROM --platform=linux/amd64 BUILD AS test\n'
                    'FROM alpine:3.21\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertEqual(set(results['other_images']), {'golang:1.24', 'alpine:3.21'})

    def test_aliases_are_scoped_to_each_dockerfile(self):
        self._write('Dockerfile', 'FROM alpine:3.21 AS builder\nFROM builder\n')
        self._write('other/Dockerfile', 'FROM builder\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertEqual(set(results['other_images']), {'alpine:3.21', 'builder'})

    def test_alias_from_scratch_or_variable_is_not_external(self):
        self._write('Dockerfile',
                    'FROM scratch AS empty\nFROM empty\n'
                    'FROM $BASE AS configured\nFROM configured\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertEqual(results['other_images'], [])
        self.assertEqual(results['chainguard_images'], [])

    def test_finds_nested_dockerfile_variants(self):
        self._write('services/api/Dockerfile.prod', 'FROM cgr.dev/chainguard/node:latest\n')
        self._write('services/worker/worker.dockerfile', 'FROM ubuntu:22.04\n')
        results = self.analyzer.analyze_repository(str(self.repo))
        self.assertEqual(results['dockerfiles_found'], 2)


if __name__ == '__main__':
    unittest.main()
