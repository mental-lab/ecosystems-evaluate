"""
Java dependency parser for Maven pom.xml files.

Complements syft by extracting proper Maven coordinates (groupId:artifactId:version)
from pom.xml files for accurate dependency reporting.
"""

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List


class JavaParser:
    """Parser for Java Maven dependencies."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_repository(self, repo_path: str) -> List[Dict[str, str]]:
        """
        Parse all pom.xml and build.gradle files in repository.
        
        Args:
            repo_path: Path to cloned repository
            
        Returns:
            List of dependency dicts with name (groupId:artifactId) and version
        """
        dependencies = []
        repo = Path(repo_path)
        
        # Find all pom.xml files
        pom_files = list(repo.rglob('pom.xml'))
        for pom_file in pom_files:
            try:
                deps = self._parse_pom_file(str(pom_file))
                dependencies.extend(deps)
            except Exception as e:
                self.logger.debug(f"Error parsing {pom_file}: {e}")
        
        # Find all Gradle files
        gradle_files = list(repo.rglob('build.gradle')) + list(repo.rglob('build.gradle.kts'))
        for gradle_file in gradle_files:
            try:
                deps = self._parse_gradle_file(str(gradle_file))
                dependencies.extend(deps)
            except Exception as e:
                self.logger.debug(f"Error parsing {gradle_file}: {e}")
        
        # Remove duplicates
        seen = set()
        unique_deps = []
        for dep in dependencies:
            key = f"{dep['name']}:{dep['version']}"
            if key not in seen:
                seen.add(key)
                unique_deps.append(dep)
        
        return unique_deps
    
    def _parse_pom_file(self, file_path: str) -> List[Dict[str, str]]:
        """
        Parse a single pom.xml file.
        
        Args:
            file_path: Path to pom.xml file
            
        Returns:
            List of dependency dicts
        """
        dependencies = []
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Extract properties from <properties> section
        properties = {}
        props_elem = root.find('.//{http://maven.apache.org/POM/4.0.0}properties')
        if props_elem is not None:
            for prop in props_elem:
                tag = prop.tag.replace('{http://maven.apache.org/POM/4.0.0}', '')
                if prop.text:
                    properties[tag] = prop.text
        
        # Extract version from parent if present
        parent = root.find('.//{http://maven.apache.org/POM/4.0.0}parent')
        if parent is not None:
            parent_version = parent.find('{http://maven.apache.org/POM/4.0.0}version')
            if parent_version is not None and parent_version.text:
                properties['project.parent.version'] = parent_version.text
        
        # Extract project version
        project_version = root.find('.//{http://maven.apache.org/POM/4.0.0}version')
        if project_version is not None and project_version.text:
            properties['project.version'] = project_version.text
        
        def resolve_property(value: str) -> str:
            """Resolve Maven property placeholders like ${property.name}"""
            if not value:
                return value
            
            pattern = r'\$\{([^}]+)\}'
            matches = re.findall(pattern, value)
            
            for prop_name in matches:
                if prop_name in properties:
                    value = value.replace(f'${{{prop_name}}}', properties[prop_name])
            
            return value
        
        # Find all dependencies
        for dep in root.findall('.//{http://maven.apache.org/POM/4.0.0}dependency'):
            group_id = dep.find('{http://maven.apache.org/POM/4.0.0}groupId')
            artifact_id = dep.find('{http://maven.apache.org/POM/4.0.0}artifactId')
            version_elem = dep.find('{http://maven.apache.org/POM/4.0.0}version')
            
            if group_id is not None and artifact_id is not None:
                package = f"{group_id.text}:{artifact_id.text}"
                version = version_elem.text if version_elem is not None else ''
                
                # Resolve property placeholders in version
                version = resolve_property(version)
                
                if version:  # Only include if we have a version
                    dependencies.append({
                        'name': package,
                        'version': version,
                        'ecosystem': 'java'
                    })
        
        return dependencies
    
    def _parse_gradle_file(self, file_path: str) -> List[Dict[str, str]]:
        """
        Parse a Gradle build file for dependencies.
        
        Args:
            file_path: Path to build.gradle or build.gradle.kts file
            
        Returns:
            List of dependency dicts
        """
        dependencies = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Pattern to match dependency declarations
            # Examples:
            #   implementation 'group:artifact:version'
            #   implementation "group:artifact:version"
            #   implementation("group:artifact:version")
            #   compile 'group:artifact:version'
            
            # Match quoted strings with group:artifact:version format
            patterns = [
                r"['\"]([a-zA-Z0-9._-]+):([a-zA-Z0-9._-]+):([a-zA-Z0-9._+-]+)['\"]",  # 'group:artifact:version'
                r'["\']([a-zA-Z0-9._-]+):([a-zA-Z0-9._-]+):([a-zA-Z0-9._+-]+)["\']',  # "group:artifact:version"
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    group_id, artifact_id, version = match
                    package = f"{group_id}:{artifact_id}"
                    
                    dependencies.append({
                        'name': package,
                        'version': version,
                        'ecosystem': 'java'
                    })
        
        except Exception as e:
            self.logger.debug(f"Error reading Gradle file {file_path}: {e}")
        
        return dependencies
