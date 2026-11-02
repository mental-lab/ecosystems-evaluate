"""Tests for SyftAnalyzer SBOM parsing (no syft binary required)."""

import unittest

from repo_analyzer.syft_analyzer import SyftAnalyzer


def _artifact(name, version, language='', artifact_type='', purl='', paths=()):
    return {
        'name': name,
        'version': version,
        'language': language,
        'type': artifact_type,
        'purl': purl,
        'locations': [{'path': p} for p in paths],
    }


class TestParseSbom(unittest.TestCase):

    def setUp(self):
        self.analyzer = SyftAnalyzer()

    def test_groups_by_ecosystem(self):
        sbom = {'artifacts': [
            _artifact('requests', '2.32.5', 'python', 'python',
                      paths=['/app/requirements.txt']),
            _artifact('lodash', '4.17.21', 'javascript', 'npm'),
            _artifact('cobra', '1.8.0', 'go', 'go-module'),
        ]}
        deps = self.analyzer.parse_sbom_to_dependencies(sbom)
        self.assertEqual([d['name'] for d in deps['python']], ['requests'])
        self.assertEqual([d['name'] for d in deps['javascript']], ['lodash'])
        self.assertEqual([d['name'] for d in deps['go']], ['cobra'])

    def test_skips_artifacts_without_name_or_version(self):
        sbom = {'artifacts': [
            _artifact('', '1.0.0', 'python', 'python'),
            _artifact('noversion', '', 'python', 'python'),
            _artifact('requests', '2.32.5', 'python', 'python'),
        ]}
        deps = self.analyzer.parse_sbom_to_dependencies(sbom)
        self.assertEqual(len(deps['python']), 1)

    def test_locations_extracted(self):
        sbom = {'artifacts': [
            _artifact('requests', '2.32.5', 'python', 'python',
                      paths=['/app/requirements.txt', '/app/setup.py']),
        ]}
        deps = self.analyzer.parse_sbom_to_dependencies(sbom)
        self.assertEqual(deps['python'][0]['locations'],
                         ['/app/requirements.txt', '/app/setup.py'])

    def test_falls_back_to_type_when_language_unknown(self):
        sbom = {'artifacts': [
            _artifact('log4j', '2.20.0', 'UnknownLanguage', 'java-archive'),
        ]}
        deps = self.analyzer.parse_sbom_to_dependencies(sbom)
        self.assertIn('java-archive', deps)

    def test_restricted_mode_filters_to_core_ecosystems(self):
        sbom = {'artifacts': [
            _artifact('requests', '2.32.5', 'python', 'python'),
            _artifact('cobra', '1.8.0', 'go', 'go-module'),
            _artifact('lodash', '4.17.21', 'javascript', 'npm'),
        ]}
        deps = self.analyzer.parse_sbom_to_dependencies(
            sbom, include_all_ecosystems=False)
        self.assertIn('python', deps)
        self.assertIn('javascript', deps)
        self.assertNotIn('go', deps)


class TestEcosystemCounts(unittest.TestCase):

    def test_get_all_ecosystems_counts(self):
        sbom = {'artifacts': [
            _artifact('a', '1.0', 'python', 'python'),
            _artifact('b', '1.0', 'python', 'python'),
            _artifact('c', '1.0', 'go', 'go-module'),
        ]}
        counts = SyftAnalyzer().get_all_ecosystems(sbom)
        self.assertEqual(counts, {'python': 2, 'go': 1})


if __name__ == '__main__':
    unittest.main()
