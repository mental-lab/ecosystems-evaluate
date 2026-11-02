"""
Syft integration for SBOM generation and dependency extraction.

Uses Syft to generate Software Bill of Materials (SBOM) from repositories.
"""

import json
import logging
import subprocess
from typing import Dict, List, Optional
from .java_parser import JavaParser


class SyftAnalyzer:
    """Wrapper for Syft SBOM generation and parsing."""
    
    def __init__(self):
        """Initialize Syft analyzer."""
        self.logger = logging.getLogger(__name__)
        self.java_parser = JavaParser()
    
    def check_syft_available(self) -> bool:
        """
        Check if syft is installed and available.
        
        Returns:
            True if syft is available, False otherwise
        """
        try:
            result = subprocess.run(
                ['syft', 'version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def analyze_repository(self, repo_path: str) -> Optional[Dict]:
        """
        Run syft on a repository to generate SBOM.
        
        Args:
            repo_path: Path to cloned repository
            
        Returns:
            Parsed SBOM data as dictionary, or None if analysis failed
        """
        try:
            self.logger.debug(f"Running syft on {repo_path}")
            
            # Run syft with JSON output
            cmd = [
                'syft',
                repo_path,
                '-o', 'json',
                '--quiet'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout for large repos
            )
            
            if result.returncode != 0:
                self.logger.error(f"Syft analysis failed: {result.stderr}")
                return None
            
            # Parse JSON output
            sbom_data = json.loads(result.stdout)
            self.logger.debug(f"Syft found {len(sbom_data.get('artifacts', []))} artifacts")
            
            return sbom_data
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Syft analysis timed out for {repo_path}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse syft output: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Syft analysis failed: {e}")
            return None
    
    def parse_sbom_to_dependencies(self, sbom_data: Dict, repo_path: str = None, include_all_ecosystems: bool = True) -> Dict[str, List[Dict]]:
        """
        Parse syft SBOM output into dependency format.
        
        Args:
            sbom_data: Raw SBOM data from syft
            repo_path: Optional path to repository for enhanced Java parsing
            include_all_ecosystems: If True, include all ecosystems detected by syft.
                                   If False, only include python/java/javascript.
            
        Returns:
            Dictionary mapping ecosystems to dependency lists
            Format: {
                'python': [{'name': 'requests', 'version': '2.28.0'}, ...],
                'java': [...],
                'javascript': [...],
                'go': [...],  # if include_all_ecosystems=True
                'rust': [...],  # if include_all_ecosystems=True
            }
        """
        dependencies_by_ecosystem = {}
        
        artifacts = sbom_data.get('artifacts', [])
        
        for artifact in artifacts:
            # Extract key information
            name = artifact.get('name', '')
            version = artifact.get('version', '')
            language = artifact.get('language', '')
            artifact_type = artifact.get('type', '')
            
            # Skip if missing critical info
            if not name or not version:
                continue
            
            # Determine ecosystem
            if include_all_ecosystems:
                # Use language if available, otherwise use type
                ecosystem = language if language else artifact_type
                if not ecosystem or ecosystem == 'UnknownLanguage':
                    ecosystem = artifact_type if artifact_type else 'unknown'
            else:
                # Only include supported ecosystems
                ecosystem = self._map_language_to_ecosystem(language, artifact_type)
                if not ecosystem:
                    continue
            
            # Initialize ecosystem list if needed
            if ecosystem not in dependencies_by_ecosystem:
                dependencies_by_ecosystem[ecosystem] = []
            
            # Add dependency
            dependencies_by_ecosystem[ecosystem].append({
                'name': name,
                'version': version,
                'purl': artifact.get('purl', ''),
                'type': artifact_type,
                'language': language,
                'locations': [loc.get('path', '') for loc in artifact.get('locations', [])]
            })
        
        # Enhance Java dependencies with proper Maven coordinates from pom.xml
        if repo_path and 'java' in dependencies_by_ecosystem:
            self._enhance_java_dependencies(dependencies_by_ecosystem, repo_path)
        
        return dependencies_by_ecosystem
    
    def _enhance_java_dependencies(self, dependencies_by_ecosystem: Dict[str, List[Dict]], repo_path: str):
        """
        Enhance Java dependencies with proper Maven coordinates from pom.xml files.
        
        Args:
            dependencies_by_ecosystem: Dictionary of dependencies by ecosystem
            repo_path: Path to repository
        """
        try:
            # Parse pom.xml files to get proper Maven coordinates
            parsed_java_deps = self.java_parser.parse_repository(repo_path)
            
            if not parsed_java_deps:
                return
            
            # Create a lookup map by artifact name for matching
            parsed_by_artifact = {}
            for dep in parsed_java_deps:
                # Extract artifact name from groupId:artifactId
                if ':' in dep['name']:
                    artifact_name = dep['name'].split(':')[-1]
                    parsed_by_artifact[artifact_name.lower()] = dep
            
            # Replace syft's Java dependencies with parsed ones that have proper coordinates
            enhanced_deps = []
            syft_artifact_names = set()
            
            # First, add all parsed dependencies with proper coordinates
            for dep in parsed_java_deps:
                enhanced_deps.append(dep)
                # Track artifact names we've added
                if ':' in dep['name']:
                    artifact_name = dep['name'].split(':')[-1]
                    syft_artifact_names.add(artifact_name.lower())
            
            # Then add any syft dependencies that weren't in pom.xml (e.g., transitive deps)
            for syft_dep in dependencies_by_ecosystem['java']:
                artifact_name = syft_dep['name'].lower()
                if artifact_name not in syft_artifact_names:
                    # Keep syft dependency as-is if not found in pom.xml
                    enhanced_deps.append(syft_dep)
            
            # Replace the java dependencies with enhanced version
            dependencies_by_ecosystem['java'] = enhanced_deps
            
            self.logger.info(f"Enhanced {len(parsed_java_deps)} Java dependencies with Maven coordinates")
            
        except Exception as e:
            self.logger.debug(f"Could not enhance Java dependencies: {e}")
    
    def _map_language_to_ecosystem(self, language: str, artifact_type: str) -> Optional[str]:
        """
        Map syft language/type to our ecosystem names.
        
        Args:
            language: Syft language field
            artifact_type: Syft type field (npm, python, java-archive, etc.)
            
        Returns:
            Ecosystem name (python, java, javascript) or None
        """
        # Direct language mapping
        language_map = {
            'python': 'python',
            'java': 'java',
            'javascript': 'javascript',
            'js': 'javascript'
        }
        
        if language.lower() in language_map:
            return language_map[language.lower()]
        
        # Type-based mapping for cases where language is not set
        type_map = {
            'python': 'python',
            'wheel': 'python',
            'egg': 'python',
            'java-archive': 'java',
            'jenkins-plugin': 'java',
            'npm': 'javascript',
            'yarn': 'javascript',
            'pnpm': 'javascript'
        }
        
        if artifact_type.lower() in type_map:
            return type_map[artifact_type.lower()]
        
        return None
    
    def get_all_ecosystems(self, sbom_data: Dict) -> Dict[str, int]:
        """
        Get all ecosystems detected by syft with counts.
        
        Useful for showing unsupported ecosystems to users.
        
        Args:
            sbom_data: Raw SBOM data from syft
            
        Returns:
            Dictionary mapping ecosystem to package count
            Format: {'python': 150, 'go': 25, 'rust': 8, ...}
        """
        ecosystem_counts = {}
        
        artifacts = sbom_data.get('artifacts', [])
        
        for artifact in artifacts:
            language = artifact.get('language', 'unknown')
            artifact_type = artifact.get('type', '')
            
            # Try to get a meaningful ecosystem name
            ecosystem = language if language else artifact_type
            
            if ecosystem:
                ecosystem_counts[ecosystem] = ecosystem_counts.get(ecosystem, 0) + 1
        
        return ecosystem_counts
