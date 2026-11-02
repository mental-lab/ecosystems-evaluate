"""
Repository Analyzer - Multi-platform Dependency Analysis Package

A tool for analyzing dependency manifests across multiple platforms:
- GitLab, GitHub, Azure DevOps
- All ecosystems detected by Syft, plus Dockerfile base images
- Organization-wide and individual repository analysis
"""

__version__ = "0.1.0"
__author__ = "Chainguard"
__description__ = "Multi-platform repository dependency analyzer"

# Core data models
from .models import RepositoryInfo, DependencyInfo, ProjectAnalysis, OrganizationAnalysis

__all__ = [
    "RepositoryInfo",
    "DependencyInfo", 
    "ProjectAnalysis",
    "OrganizationAnalysis",
]
