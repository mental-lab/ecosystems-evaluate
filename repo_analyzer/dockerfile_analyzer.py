"""
Dockerfile analyzer for detecting Chainguard image adoption.

Scans Dockerfiles to identify base images and detect Chainguard usage.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional


class DockerfileAnalyzer:
    """Analyzes Dockerfiles to detect Chainguard image adoption."""
    
    CHAINGUARD_PATTERNS = [
        r'cgr\.dev',
        r'chainguard',
        r'images\.chainguard\.dev'
    ]
    
    def __init__(self):
        """Initialize Dockerfile analyzer."""
        self.logger = logging.getLogger(__name__)
    
    def analyze_repository(self, repo_path: str) -> Dict[str, any]:
        """
        Scan repository for Dockerfiles and analyze base images.
        
        Args:
            repo_path: Path to cloned repository
            
        Returns:
            Dictionary with Dockerfile analysis results:
            {
                'dockerfiles_found': 3,
                'chainguard_images': ['python:latest', 'node:20'],
                'other_images': ['ubuntu:22.04'],
                'adoption_detected': True
            }
        """
        results = {
            'dockerfiles_found': 0,
            'chainguard_images': [],
            'other_images': [],
            'adoption_detected': False,
            'dockerfiles': []  # List of {path, chainguard_images, other_images}
        }
        
        # Find all Dockerfiles
        dockerfiles = self._find_dockerfiles(repo_path)
        results['dockerfiles_found'] = len(dockerfiles)
        
        if not dockerfiles:
            return results
        
        repo = Path(repo_path)
        
        # Analyze each Dockerfile
        for dockerfile_path in dockerfiles:
            images = self._parse_dockerfile(dockerfile_path)
            
            dockerfile_info = {
                'path': str(dockerfile_path.relative_to(repo)),
                'chainguard_images': [],
                'other_images': []
            }
            
            for image in images:
                if self._is_chainguard_image(image):
                    results['chainguard_images'].append(image)
                    dockerfile_info['chainguard_images'].append(image)
                    results['adoption_detected'] = True
                else:
                    results['other_images'].append(image)
                    dockerfile_info['other_images'].append(image)
            
            results['dockerfiles'].append(dockerfile_info)
        
        # Remove duplicates from summary lists
        results['chainguard_images'] = list(set(results['chainguard_images']))
        results['other_images'] = list(set(results['other_images']))
        
        return results
    
    def _find_dockerfiles(self, repo_path: str) -> List[Path]:
        """
        Find all Dockerfiles in repository.
        
        Args:
            repo_path: Path to repository
            
        Returns:
            List of Dockerfile paths
        """
        dockerfiles = []
        repo = Path(repo_path)
        
        # Find all files recursively and check if they match Dockerfile patterns
        for file_path in repo.rglob('*'):
            if not file_path.is_file():
                continue
            
            filename = file_path.name.lower()
            
            # Match various Dockerfile patterns (case-insensitive)
            if (filename == 'dockerfile' or 
                filename.startswith('dockerfile.') or 
                filename.endswith('.dockerfile')):
                dockerfiles.append(file_path)
        
        return dockerfiles
    
    def _parse_dockerfile(self, dockerfile_path: Path) -> List[str]:
        """
        Parse Dockerfile and extract base images.
        
        Args:
            dockerfile_path: Path to Dockerfile
            
        Returns:
            List of base image names
        """
        images = []
        
        try:
            content = dockerfile_path.read_text(errors='ignore')
            
            # Match FROM statements
            # FROM image:tag
            # FROM image:tag AS stage
            # FROM --platform=linux/amd64 image:tag
            from_pattern = r'^\s*FROM\s+(?:--platform=[^\s]+\s+)?([^\s]+)(?:\s+AS\s+([^\s]+))?'
            stages = set()
            
            for line in content.split('\n'):
                match = re.match(from_pattern, line, re.IGNORECASE)
                if match:
                    image = match.group(1)
                    # Skip build stages (they reference previous stages)
                    if (not image.startswith('$') and image.lower() != 'scratch'
                            and image.lower() not in stages):
                        images.append(image)
                    # Aliases are local to this Dockerfile and may reference
                    # either an external image or an earlier stage.
                    alias = match.group(2)
                    if alias:
                        stages.add(alias.lower())
        
        except Exception as e:
            self.logger.debug(f"Failed to parse {dockerfile_path}: {e}")
        
        return images
    
    def _is_chainguard_image(self, image: str) -> bool:
        """
        Check if image is from Chainguard.
        
        Args:
            image: Image name (e.g., 'cgr.dev/chainguard/python:latest')
            
        Returns:
            True if Chainguard image, False otherwise
        """
        image_lower = image.lower()
        
        for pattern in self.CHAINGUARD_PATTERNS:
            if re.search(pattern, image_lower):
                return True
        
        return False
    
    def get_adoption_summary(self, results: Dict) -> str:
        """
        Generate human-readable adoption summary.
        
        Args:
            results: Results from analyze_repository
            
        Returns:
            Summary string
        """
        if not results['dockerfiles_found']:
            return "No Dockerfiles found"
        
        if results['adoption_detected']:
            cg_count = len(results['chainguard_images'])
            other_count = len(results['other_images'])
            total = cg_count + other_count
            percentage = (cg_count / total * 100) if total > 0 else 0
            
            return f"{cg_count}/{total} images using Chainguard ({percentage:.1f}%)"
        else:
            return f"0/{len(results['other_images'])} images using Chainguard"
