"""
Azure DevOps repository analyzer.

This module handles:
- Azure DevOps API authentication with Personal Access Tokens
- Organization and project repository discovery
- Individual repository access
- Cross-project repository analysis
"""

import base64
import logging
import requests
import time
from typing import List, Optional
from urllib.parse import urljoin

from .models import RepositoryInfo
from .platform_analyzers import PlatformAnalyzer


class AzureDevOpsAnalyzer(PlatformAnalyzer):
    """Analyzer for Azure DevOps repositories with production-tested patterns."""
    
    def __init__(self, source_url: str, token: str, ssl_verify: bool = True):
        """Initialize with session management and enhanced error handling."""
        super().__init__(source_url, token, ssl_verify)
        
        # Additional Azure DevOps specific setup
        # (Base class already handles session, SSL, and retry logic)
        
        # API version parameter
        self.api_params = {'api-version': '7.2-preview'}
    
    def _get_auth_headers(self) -> dict[str, str]:
        """Azure DevOps uses basic authentication with PAT tokens."""
        auth_string = base64.b64encode(f':{self.token}'.encode()).decode()
        return {
            'Authorization': f'Basic {auth_string}',
            'Content-Type': 'application/json'
        }
    
    def _generate_request_url(self, api_path: str, org_name: str, sub_api: str = None) -> str:
        """Generate Azure DevOps API URL with subdomain support."""
        base_url = self.source_url
        
        # Handle dev.azure.com subdomain routing
        if sub_api and "dev.azure.com" in self.source_url:
            base_url_parts = base_url.split("://", 1)
            base_url = f"{base_url_parts[0]}://{sub_api}.{base_url_parts[1]}"
        
        return urljoin(base_url + '/', f"{org_name}/{api_path}")
    
    def _make_paginated_request(self, url: str, params: dict = None) -> List[dict]:
        """Make paginated requests with continuation tokens."""
        all_results = []
        request_params = {**self.api_params, **(params or {})}
        
        while True:
            try:
                response = self.session.get(url, params=request_params, timeout=self.timeout)
                response.raise_for_status()
                
                data = response.json()
                
                # Handle Azure DevOps response format
                if 'value' in data:
                    all_results.extend(data['value'])
                elif isinstance(data, list):
                    all_results.extend(data)
                else:
                    all_results.append(data)
                
                # Check for continuation token
                continuation_token = None
                for header_name, header_value in response.headers.items():
                    if header_name.lower() == "x-ms-continuationtoken":
                        continuation_token = header_value
                        break
                
                if not continuation_token:
                    break
                
                # Set continuation token for next request
                request_params["continuationToken"] = continuation_token
                
                # Rate limiting
                self._handle_rate_limiting(response.headers)
                
            except requests.exceptions.RequestException as e:
                # Auth failures are not transient — surface them to the caller
                response = getattr(e, 'response', None)
                if response is not None and response.status_code in (401, 403):
                    raise
                logging.error(f"Error in paginated request to {url}: {e}")
                break
        
        return all_results
    
    def _handle_rate_limiting(self, headers: dict) -> None:
        """Handle Azure DevOps rate limiting."""
        # Azure DevOps rate limiting headers
        if 'X-RateLimit-Remaining' in headers:
            remaining = int(headers.get('X-RateLimit-Remaining', 100))
            if remaining < 10:  # Conservative threshold
                reset_time = headers.get('X-RateLimit-Reset')
                if reset_time:
                    wait_time = max(1, int(reset_time) - int(time.time()))
                    logging.info(f"Rate limit approaching, waiting {wait_time} seconds")
                    time.sleep(wait_time)
    
    def get_repositories(self, org_name: str) -> List[RepositoryInfo]:
        """Get all repositories in an Azure DevOps organization.
        
        Args:
            org_name: Azure DevOps organization name
            
        Returns:
            List of RepositoryInfo objects for all repositories across all projects
        """
        repos = []
        
        try:
            # First get all projects in the organization with pagination
            projects_url = f"{self.source_url}/{org_name}/_apis/projects"
            projects = self._make_paginated_request(projects_url)
            
            for project in projects:
                project_name = project['name']
                project_id = project['id']
                
                # Get repositories for this project with pagination
                repos_url = f"{self.source_url}/{org_name}/{project_name}/_apis/git/repositories"
                
                try:
                    project_repos = self._make_paginated_request(repos_url)
                    
                    for repo in project_repos:
                        repo_info = RepositoryInfo(
                            name=repo['name'],
                            url=repo['webUrl'],
                            platform='ado',
                            default_branch=repo.get('defaultBranch', 'main').replace('refs/heads/', ''),
                            project_id=f"{project_name}/{repo['name']}",
                            language=None,  # Azure DevOps doesn't provide language in repo list
                            description=None
                        )
                        repos.append(repo_info)
                        
                except Exception as e:
                    logging.error(f"Error fetching repositories for project {project_name}: {e}")
                    continue
                    
        except Exception as e:
            logging.error(f"Error fetching projects for organization {org_name}: {e}")
            
        return repos
    
    def get_single_repository(self, repo_path: str) -> Optional[RepositoryInfo]:
        """Get information for a single Azure DevOps repository.
        
        Args:
            repo_path: Repository path in format 'project/repository'
            
        Returns:
            RepositoryInfo object or None if not found
        """
        try:
            # Parse project and repo from path
            if '/' not in repo_path:
                logging.error(f"Invalid repository path format: {repo_path}. Expected 'project/repository'")
                return None
                
            project_name, repo_name = repo_path.split('/', 1)
            
            # Extract organization from source URL
            org_name = self.source_url.rstrip('/').split('/')[-1]
            
            repo_url = f"{self.source_url}/{org_name}/{project_name}/_apis/git/repositories/{repo_name}"
            
            response = self.session.get(repo_url, params=self.api_params, timeout=self.timeout)
            response.raise_for_status()
            
            repo_data = response.json()
            
            return RepositoryInfo(
                name=repo_data['name'],
                url=repo_data['webUrl'],
                platform='ado',
                default_branch=repo_data.get('defaultBranch', 'main').replace('refs/heads/', ''),
                project_id=f"{project_name}/{repo_data['name']}",
                language=None,
                description=None
            )
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching repository {repo_path}: {e}")
            return None
    
    def get_file_content(self, repo_info: RepositoryInfo, file_path: str) -> Optional[str]:
        """Get file content from an Azure DevOps repository.
        
        Args:
            repo_info: Repository information
            file_path: Path to the file in the repository
            
        Returns:
            File content as string or None if not found
        """
        try:
            # Parse project and repo from project_id
            project_name, repo_name = repo_info.project_id.split('/', 1)
            
            # Extract organization from source URL
            org_name = self.source_url.rstrip('/').split('/')[-1]
            
            # Azure DevOps file content API
            file_url = f"{self.source_url}/{org_name}/{project_name}/_apis/git/repositories/{repo_name}/items"
            
            params = {
                **self.api_params,
                'path': f"/{file_path}",
                'includeContent': 'true'
            }
            
            response = self.session.get(file_url, params=params, timeout=self.timeout)
            
            if response.status_code == 404:
                return None
                
            response.raise_for_status()
            return response.text
            
        except requests.exceptions.RequestException as e:
            logging.debug(f"File {file_path} not found in {repo_info.name}: {e}")
            return None