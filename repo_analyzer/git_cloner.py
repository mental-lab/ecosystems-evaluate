"""
Git clone operations for repository analysis.

Handles shallow cloning of repositories with authentication and cleanup.
"""

import base64
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class GitCloner:
    """Manages git clone operations for dependency analysis."""
    
    def __init__(self, token: Optional[str] = None, platform: Optional[str] = None):
        """
        Initialize git cloner.
        
        Args:
            token: Authentication token for private repositories
            platform: Platform name ('github', 'gitlab', 'ado') to select auth scheme
        """
        self.token = token
        self.platform = (platform or '').lower()
        self.logger = logging.getLogger(__name__)
    
    def shallow_clone(self, repo_url: str, branch: Optional[str] = None) -> Optional[str]:
        """
        Perform a shallow clone of a repository.
        
        Args:
            repo_url: Repository URL (https://github.com/org/repo.git)
            branch: Specific branch to clone (default: repository default branch)
            
        Returns:
            Path to cloned repository, or None if clone failed
        """
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix='ecosystems-evaluate-')
            
            # Build git clone command
            cmd = [
                'git', 'clone',
                '--depth=1',           # Only latest commit
                '--single-branch',     # Only default branch
                '--quiet'              # Suppress output
            ]
            
            if branch:
                cmd.extend(['--branch', branch])
            
            cmd.extend([repo_url, temp_dir])
            
            # Pass auth via git config env vars so the token never appears
            # in the clone URL or in the process argument list
            env = self._build_auth_env()
            
            # Execute clone
            self.logger.debug(f"Cloning {repo_url} to {temp_dir}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 60 second timeout
                env=env
            )
            
            if result.returncode != 0:
                self.logger.error(f"Git clone failed: {self._redact(result.stderr)}")
                self.cleanup(temp_dir)
                return None
            
            self.logger.debug(f"Successfully cloned to {temp_dir}")
            return temp_dir
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Git clone timed out for {repo_url}")
            if temp_dir:
                self.cleanup(temp_dir)
            return None
        except Exception as e:
            self.logger.error(f"Git clone failed: {self._redact(str(e))}")
            if temp_dir:
                self.cleanup(temp_dir)
            return None
    
    def _build_auth_env(self) -> dict:
        """
        Build environment for git subprocess with auth config injected.
        
        Uses GIT_CONFIG_COUNT/GIT_CONFIG_KEY_*/GIT_CONFIG_VALUE_* (git >= 2.31)
        to set http.extraHeader so the token is never embedded in the remote
        URL, written into .git/config, or exposed in the process arguments.
        
        Returns:
            Environment dict for subprocess.run
        """
        env = os.environ.copy()
        auth_header = self._get_auth_header()
        if auth_header:
            env['GIT_CONFIG_COUNT'] = '1'
            env['GIT_CONFIG_KEY_0'] = 'http.extraHeader'
            env['GIT_CONFIG_VALUE_0'] = auth_header
        return env
    
    def _get_auth_header(self) -> Optional[str]:
        """
        Get the Authorization header value for git HTTP requests.
        
        Returns:
            Authorization header value, or None if no token configured
        """
        if not self.token:
            return None
        if self.platform == 'ado':
            # Azure DevOps PATs use Basic auth with empty username
            encoded = base64.b64encode(f':{self.token}'.encode()).decode()
            return f'Authorization: Basic {encoded}'
        if self.platform == 'github':
            # GitHub's git HTTP endpoints require Basic auth — Bearer is only
            # honored by the REST/GraphQL APIs (fine-grained PATs included)
            encoded = base64.b64encode(f'x-access-token:{self.token}'.encode()).decode()
            return f'Authorization: Basic {encoded}'
        # GitLab accepts Bearer tokens for HTTPS git operations
        return f'Authorization: Bearer {self.token}'
    
    def _redact(self, text: str) -> str:
        """
        Redact the auth token from text before logging.
        
        Args:
            text: Text that may contain the token (stderr, exception messages)
            
        Returns:
            Text with token occurrences replaced
        """
        if self.token and text:
            return text.replace(self.token, '***')
        return text
    
    def cleanup(self, clone_path: str) -> None:
        """
        Remove cloned repository directory.
        
        Args:
            clone_path: Path to cloned repository
        """
        try:
            if clone_path and os.path.exists(clone_path):
                shutil.rmtree(clone_path)
                self.logger.debug(f"Cleaned up {clone_path}")
        except Exception as e:
            self.logger.warning(f"Failed to cleanup {clone_path}: {e}")
    
    def check_git_available(self) -> bool:
        """
        Check if git is installed and available.
        
        Returns:
            True if git is available, False otherwise
        """
        try:
            result = subprocess.run(
                ['git', '--version'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
