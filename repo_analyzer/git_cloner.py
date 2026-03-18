"""
Git clone operations for repository analysis.

Handles shallow cloning of repositories with authentication and cleanup.
"""

import logging
import os
import shutil
import stat
import subprocess
import tempfile
from typing import Optional


class GitCloner:
    """Manages git clone operations for dependency analysis."""

    def __init__(self, token: Optional[str] = None):
        """
        Initialize git cloner.

        Args:
            token: Authentication token for private repositories
        """
        self.token = token
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
        temp_dir = None
        askpass_script = None
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix='ecosystems-evaluate-')

            # Build git clone command (plain URL, no embedded token)
            cmd = [
                'git', 'clone',
                '--depth=1',           # Only latest commit
                '--single-branch',     # Only default branch
                '--quiet'              # Suppress output
            ]

            if branch:
                cmd.extend(['--branch', branch])

            cmd.extend([repo_url, temp_dir])

            # Set up environment for authentication
            env = os.environ.copy()
            if self.token:
                askpass_script = self._create_askpass_script(self.token)
                env['GIT_ASKPASS'] = askpass_script
                env['GIT_TERMINAL_PROMPT'] = '0'

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
                self.logger.error(f"Git clone failed: {result.stderr}")
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
            self.logger.error(f"Git clone failed: {e}")
            if temp_dir:
                self.cleanup(temp_dir)
            return None
        finally:
            if askpass_script and os.path.exists(askpass_script):
                os.unlink(askpass_script)

    def _create_askpass_script(self, token: str) -> str:
        """
        Create a temporary GIT_ASKPASS script that provides the auth token.

        Using GIT_ASKPASS avoids embedding the token in the clone URL, which
        would expose it in process argument lists and git remote configs.

        Args:
            token: GitHub authentication token

        Returns:
            Path to the temporary askpass script
        """
        fd, script_path = tempfile.mkstemp(prefix='git-askpass-', suffix='.sh')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write('#!/bin/sh\n')
                f.write(f'echo {token}\n')
            os.chmod(script_path, stat.S_IRWXU)  # 0700 — owner only
        except Exception:
            os.unlink(script_path)
            raise
        return script_path

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
