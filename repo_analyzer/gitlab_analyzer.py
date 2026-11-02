"""
GitLab repository analyzer.

This module handles:
- GitLab API authentication with Bearer tokens
- Group/subgroup repository discovery
- Individual repository access
- File content retrieval from GitLab repositories

Separated from platform_analyzers.py for:
- Single Responsibility: Only GitLab-specific logic
- Easier testing: Can test GitLab functionality independently
- Better maintainability: Changes to GitLab API only affect this file
"""

import logging
import requests
from typing import List, Optional

from .models import RepositoryInfo
from .platform_analyzers import PlatformAnalyzer


class GitLabAnalyzer(PlatformAnalyzer):
    """Analyzer for GitLab repositories."""

    def _get_auth_headers(self) -> dict[str, str]:
        """GitLab uses Bearer token authentication."""
        return {'Authorization': f'Bearer {self.token}'}

    def get_repositories(self, group_id: str) -> List[RepositoryInfo]:
        """Get all projects in a GitLab group.

        Args:
            group_id: GitLab group ID or group path

        Returns:
            List of RepositoryInfo objects for all projects in the group

        """
        projects = []

        # Handle both group ID and group path
        group_param = group_id
        if not group_id.isdigit():
            group_param = requests.utils.quote(group_id, safe='')

        page = 1
        per_page = 100

        while True:
            url = f"{self.source_url}/api/v4/groups/{group_param}/projects"
            params = {
                'page': page,
                'per_page': per_page,
                'include_subgroups': 'true',  # Include nested groups
                'simple': 'true'              # Reduce response size
            }

            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()

            # Handle rate limiting
            self._handle_rate_limiting(response.headers, "GitLab")

            batch_projects = response.json()
            if not batch_projects:
                break

            for project in batch_projects:
                projects.append(RepositoryInfo(
                    name=project['name'],
                    url=project['web_url'],
                    platform='gitlab',
                    project_id=str(project['id']),
                    default_branch=project.get('default_branch', 'main'),
                    language=project.get('language'),
                    description=project.get('description')
                ))

            page += 1

        return projects

    def get_single_repository(self, repo_spec: str) -> RepositoryInfo:
        """Get single GitLab repository info.

        Args:
            repo_spec: Repository specification (group/project format)

        Returns:
            RepositoryInfo object for the specified repository
        """
        project_param = requests.utils.quote(repo_spec, safe='')
        url = f"{self.source_url}/api/v4/projects/{project_param}"

        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        
        # Handle rate limiting
        self._handle_rate_limiting(response.headers, "GitLab")

        project = response.json()
        return RepositoryInfo(
            name=project['name'],
            url=project['web_url'],
            platform='gitlab',
            project_id=str(project['id']),
            default_branch=project.get('default_branch', 'main'),
            language=project.get('language'),
            description=project.get('description')
        )

    def get_file_content(self, repo_info: RepositoryInfo, file_path: str) -> Optional[str]:
        """Get file content from GitLab repository.

        Args:
            repo_info: Repository information
            file_path: Path to file in repository

        Returns:
            File content as string, or None if file doesn't exist
        """
        try:
            project_id = repo_info.project_id or repo_info.name
            file_param = requests.utils.quote(file_path, safe='')
            url = f"{self.source_url}/api/v4/projects/{project_id}/repository/files/{file_param}/raw"
            params = {'ref': repo_info.default_branch}

            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                # Handle rate limiting
                self._handle_rate_limiting(response.headers, "GitLab")
                return response.text
        except Exception as e:
            logging.debug(f"Could not get {file_path} from {repo_info.name}: {e}")

        return None
