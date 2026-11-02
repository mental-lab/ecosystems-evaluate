from dataclasses import dataclass
from typing import Dict, List, Any, Optional


@dataclass
class RepositoryInfo:
    """Information about a repository."""
    name: str
    url: str
    platform: str
    default_branch: str
    project_id: Optional[str] = None
    language: Optional[str] = None
    description: Optional[str] = None


@dataclass
class DependencyInfo:
    """Dependency information from a manifest file."""
    file_path: str
    file_type: str
    ecosystem: str
    dependencies: List[Dict[str, str]]
    build_tool: Optional[str] = None


@dataclass
class ProjectAnalysis:
    """Analysis for a single project."""
    repository: RepositoryInfo
    manifests: List[DependencyInfo]
    total_dependencies: int
    collection_timestamp: str
    note: str = ""
    dockerfile_adoption: Optional[Dict[str, Any]] = None


@dataclass
class SkippedRepository:
    """Information about a skipped repository."""
    name: str
    url: str
    reason: str
    error_details: Optional[str] = None


@dataclass
class OrganizationAnalysis:
    """Analysis results for an entire organization."""
    organization_name: str
    platform: str
    timestamp: str
    total_projects: int
    analyzed_projects: int
    total_dependencies: int
    projects: List[ProjectAnalysis]
    ecosystems_breakdown: Dict[str, Dict[str, Any]]
    skipped_projects: List[SkippedRepository] = None
    
    def __post_init__(self):
        if self.skipped_projects is None:
            self.skipped_projects = []
