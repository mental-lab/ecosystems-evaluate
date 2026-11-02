"""
GitHub repository analyzer.

This module handles:
- GitHub API authentication with tokens
- Organization and user repository discovery
- Individual repository access
- File content retrieval from GitHub repositories
- Auto-detection of user vs organization accounts

"""

import base64
import logging
import requests
from typing import List, Optional

from .models import RepositoryInfo
from .platform_analyzers import PlatformAnalyzer


class GitHubAnalyzer(PlatformAnalyzer):
    """Analyzer for GitHub repositories."""
    
    def _get_auth_headers(self) -> dict[str, str]:
        """GitHub uses token authentication."""
        return {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
    
    def _api_base(self) -> str:
        """Get the REST API base URL for github.com or GitHub Enterprise."""
        if 'github.com' in self.source_url:
            return 'https://api.github.com'
        return f"{self.source_url}/api/v3"
    
    def _get_repo_spec(self, repo_info: RepositoryInfo) -> str:
        """Extract 'owner/repo' spec from repository info."""
        if '/' in repo_info.name:
            return repo_info.name
        # Extract from URL
        return '/'.join(repo_info.url.split('/')[-2:])
    
    def get_repositories(self, org_name: str) -> List[RepositoryInfo]:
        """Get all repositories for a GitHub organization or user.
        
        Args:
            org_name: GitHub organization or username
            
        Returns:
            List of RepositoryInfo objects for all accessible repositories
            
        """
        repos = []
        
        # First, determine if this is a user or organization
        account_type = self._detect_account_type(org_name)
        
        page = 1
        per_page = 100
        
        while True:
            if 'github.com' in self.source_url:
                if account_type == 'Organization':
                    url = f"https://api.github.com/orgs/{org_name}/repos"
                else:
                    url = f"https://api.github.com/users/{org_name}/repos"
            else:
                # GitHub Enterprise
                if account_type == 'Organization':
                    url = f"{self.source_url}/api/v3/orgs/{org_name}/repos"
                else:
                    url = f"{self.source_url}/api/v3/users/{org_name}/repos"
            
            params = {'page': page, 'per_page': per_page}
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            # Handle rate limiting
            self._handle_rate_limiting(response.headers, "GitHub")
            
            batch_repos = response.json()
            if not batch_repos:
                break
                
            for repo in batch_repos:
                repos.append(RepositoryInfo(
                    name=repo['name'],
                    url=repo['html_url'],
                    platform='github',
                    project_id=str(repo['id']),
                    default_branch=repo.get('default_branch', 'main'),
                    language=repo.get('language'),
                    description=repo.get('description')
                ))
            
            page += 1
            
        return repos
    
    def _detect_account_type(self, account_name: str) -> str:
        """Detect if account is a User or Organization.
        
        Args:
            account_name: GitHub account name to check
            
        Returns:
            'Organization' or 'User' based on GitHub API response
        """
        if 'github.com' in self.source_url:
            url = f"https://api.github.com/users/{account_name}"
        else:
            url = f"{self.source_url}/api/v3/users/{account_name}"
        try:
            # Use requests directly with headers since session might not be configured yet
            headers = self._get_auth_headers()
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Handle rate limiting
            self._handle_rate_limiting(response.headers, "GitHub")
            
            account_info = response.json()
            account_type = account_info.get('type', 'User')
            logging.info(f"Detected account type for {account_name}: {account_type}")
            return account_type
        except Exception as e:
            logging.warning(f"Could not determine account type for {account_name}: {e}. Defaulting to Organization")
            # If we can't determine, default to Organization for backward compatibility
            return 'Organization'
    
    def get_single_repository(self, repo_spec: str) -> RepositoryInfo:
        """Get single GitHub repository info.
        
        Args:
            repo_spec: Repository specification (owner/repo format)
            
        Returns:
            RepositoryInfo object for the specified repository
        """
        if 'github.com' in self.source_url:
            url = f"https://api.github.com/repos/{repo_spec}"
        else:
            url = f"{self.source_url}/api/v3/repos/{repo_spec}"
        
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        
        # Handle rate limiting
        self._handle_rate_limiting(response.headers, "GitHub")
        
        repo = response.json()
        return RepositoryInfo(
            name=repo['name'],
            url=repo['html_url'],
            platform='github',
            project_id=str(repo['id']),
            default_branch=repo.get('default_branch', 'main'),
            language=repo.get('language'),
            description=repo.get('description')
        )
    
    def get_file_content(self, repo_info: RepositoryInfo, file_path: str) -> Optional[str]:
        """Get file content from GitHub repository.
        
        Args:
            repo_info: Repository information
            file_path: Path to file in repository
            
        Returns:
            File content as string, or None if file doesn't exist
            
        """
        try:
            repo_spec = self._get_repo_spec(repo_info)
            url = f"{self._api_base()}/repos/{repo_spec}/contents/{file_path}"
            
            params = {'ref': repo_info.default_branch}
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                # Handle rate limiting
                self._handle_rate_limiting(response.headers, "GitHub")
                
                # GitHub returns base64-encoded content
                content_data = response.json()
                if content_data.get('encoding') == 'base64':
                    return base64.b64decode(content_data['content']).decode('utf-8')
                return content_data.get('content', '')
        except Exception as e:
            logging.debug(f"Could not get {file_path} from {repo_info.name}: {e}")
        
        return None
