"""
Multi-platform dependency analyzer for GitLab, GitHub, and Azure DevOps.

Simple Usage:
    >>> analyzer = RepositoryAnalyzer(platform='gitlab', url='https://gitlab.com', token='your-token')
    >>> results = analyzer.analyze_organization('my-org')
    >>> analyzer.save_results(results, 'output.json')

Supported Platforms: gitlab, github, ado
Supported Ecosystems: all languages detected by Syft (Python, Java,
JavaScript, Go, Rust, Ruby, .NET, and more), plus Dockerfile base images
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import OrganizationAnalysis, ProjectAnalysis, RepositoryInfo, DependencyInfo, SkippedRepository
from .platform_analyzers import get_analyzer
from .git_cloner import GitCloner
from .syft_analyzer import SyftAnalyzer
from .dockerfile_analyzer import DockerfileAnalyzer


class RepositoryAnalyzer:
    """Simple, secure analyzer for multi-platform dependency analysis.

    Args:
        platform: Platform name ('gitlab', 'github', 'ado')
        url: Platform URL (e.g., 'https://gitlab.com')
        token: Authentication token
        max_workers: Number of parallel workers (default: 4)

    Example:
        >>> analyzer = RepositoryAnalyzer('gitlab', 'https://gitlab.com', 'token')
        >>> results = analyzer.analyze_organization('my-company')
        >>> print(f"Found {results.total_dependencies} dependencies")
    """

    # Supported platforms (for user reference). Ecosystem detection is
    # handled by Syft; every detected ecosystem is reported.
    SUPPORTED_PLATFORMS = ['gitlab', 'github', 'ado']

    def __init__(self, platform: str, url: str, token: str, max_workers: int = 4):
        """Initialize analyzer with platform credentials."""
        self.platform = platform.lower()
        self.url = url
        self.token = token
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)

        # Validate inputs early
        if self.platform not in self.SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Unsupported platform '{platform}'. "
                f"Supported: {', '.join(self.SUPPORTED_PLATFORMS)}"
            )

        # Create platform-specific analyzer (only for listing repos)
        self._analyzer = get_analyzer(self.platform, self.url, self.token)
        
        # Create git cloner, syft analyzer, and dockerfile analyzer
        self.git_cloner = GitCloner(token=self.token, platform=self.platform)
        self.syft_analyzer = SyftAnalyzer()
        self.dockerfile_analyzer = DockerfileAnalyzer()
        
        # Check dependencies
        if not self.git_cloner.check_git_available():
            raise RuntimeError("git is not installed or not available in PATH")
        
        if not self.syft_analyzer.check_syft_available():
            raise RuntimeError("syft is not installed or not available in PATH. Install from: https://github.com/anchore/syft")

    def analyze_organization(self, organization: str, branch: Optional[str] = None) -> OrganizationAnalysis:
        """Analyze all repositories in an organization for dependencies.

        Args:
            organization: Organization/group name to analyze
            branch: Specific branch to analyze (default: repository default branch)

        Returns:
            OrganizationAnalysis with all discovered dependencies

        Example:
            >>> results = analyzer.analyze_organization('my-company')
            >>> print(f"Analyzed {results.analyzed_projects} projects")
        """
        self.logger.info(f"Analyzing organization '{organization}' on {self.platform}")

        # Get all repositories
        repositories = self._analyzer.get_repositories(organization)
        self.logger.info(f"Found {len(repositories)} repositories")

        # Analyze all repositories
        return self._analyze_repositories(organization, repositories, branch=branch)

    def analyze_repository(self, repository: str, branch: Optional[str] = None) -> OrganizationAnalysis:
        """Analyze a single repository for dependencies.

        Args:
            repository: Repository identifier (e.g., 'group/project' for GitLab)
            branch: Specific branch to analyze (default: repository default branch)

        Returns:
            OrganizationAnalysis with discovered dependencies

        Example:
            >>> results = analyzer.analyze_repository('mygroup/myproject')
            >>> print(f"Found {results.total_dependencies} dependencies")
        """
        self.logger.info(f"Analyzing repository '{repository}' on {self.platform}")

        # Get single repository
        repo_info = self._analyzer.get_single_repository(repository)

        # Analyze it
        return self._analyze_repositories(repository, [repo_info], branch=branch)
    
    def _analyze_repositories(
        self, org_name: str, repositories: List[RepositoryInfo], branch: Optional[str] = None
    ) -> OrganizationAnalysis:
        """Analyze a list of repositories for dependencies (internal method)."""
        organization_analysis = OrganizationAnalysis(
            organization_name=org_name,
            platform=self.platform,
            timestamp=self._get_timestamp(),
            total_projects=len(repositories),
            analyzed_projects=0,
            total_dependencies=0,
            projects=[],
            ecosystems_breakdown={},
        )

        # Analyze repositories in parallel for speed
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_repo = {
                executor.submit(self._analyze_single_repository, repo, branch): repo
                for repo in repositories
            }

            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    project_analysis = future.result()
                    if project_analysis:
                        organization_analysis.projects.append(project_analysis)
                        organization_analysis.analyzed_projects += 1
                        organization_analysis.total_dependencies += (
                            project_analysis.total_dependencies
                        )

                        self.logger.info(
                            f"{repo.name}: {project_analysis.total_dependencies} dependencies"
                        )
                    else:
                        # Repository was skipped (no dependencies found)
                        skipped = SkippedRepository(
                            name=repo.name,
                            url=repo.url,
                            reason="No dependencies found",
                            error_details="Repository analyzed but no manifest files or dependencies detected"
                        )
                        organization_analysis.skipped_projects.append(skipped)
                        self.logger.info(f"{repo.name}: Skipped - no dependencies found")

                except Exception as e:
                    # Repository analysis failed
                    skipped = SkippedRepository(
                        name=repo.name,
                        url=repo.url,
                        reason="Analysis failed",
                        error_details=str(e)
                    )
                    organization_analysis.skipped_projects.append(skipped)
                    self.logger.error(f"Failed to analyze {repo.name}: {e}")

        # Calculate ecosystems breakdown
        organization_analysis.ecosystems_breakdown = self._calculate_ecosystems_breakdown(
            organization_analysis.projects
        )

        self.logger.info(
            f"Complete: {organization_analysis.analyzed_projects}/"
            f"{organization_analysis.total_projects} projects, "
            f"{organization_analysis.total_dependencies} total dependencies"
        )

        return organization_analysis
    
    def _analyze_single_repository(
        self, repo_info: RepositoryInfo, branch: Optional[str] = None
    ) -> Optional[ProjectAnalysis]:
        """Analyze a single repository using git clone + syft."""
        clone_path = None
        try:
            # Clone repository
            # Use specified branch if provided, otherwise use repository's default branch
            target_branch = branch if branch else repo_info.default_branch
            self.logger.debug(f"Cloning {repo_info.name} (branch: {target_branch})...")
            clone_path = self.git_cloner.shallow_clone(
                repo_info.url,
                branch=target_branch
            )
            
            if not clone_path:
                self.logger.warning(f"Failed to clone {repo_info.name}")
                return None
            
            # Run syft analysis
            self.logger.debug(f"Running syft on {repo_info.name}...")
            sbom_data = self.syft_analyzer.analyze_repository(clone_path)
            
            if not sbom_data:
                self.logger.warning(f"Syft analysis failed for {repo_info.name}")
                return None
            
            # Analyze Dockerfiles for Chainguard image adoption
            self.logger.debug(f"Analyzing Dockerfiles in {repo_info.name}...")
            dockerfile_results = self.dockerfile_analyzer.analyze_repository(clone_path)
            
            # Parse SBOM into our dependency format (with Java enhancement)
            dependencies_by_ecosystem = self.syft_analyzer.parse_sbom_to_dependencies(sbom_data, repo_path=clone_path)
            
            # Check if we found anything useful
            has_dependencies = dependencies_by_ecosystem and any(len(deps) > 0 for deps in dependencies_by_ecosystem.values())
            has_dockerfiles = dockerfile_results['dockerfiles_found'] > 0
            
            if not has_dependencies and not has_dockerfiles:
                self.logger.debug(f"No dependencies or Dockerfiles found in {repo_info.name}")
                return None
            
            # Convert to manifest format
            manifests = []
            total_deps = 0
            
            for ecosystem, deps in dependencies_by_ecosystem.items():
                if deps:
                    # Get unique file paths from dependencies
                    file_paths = set()
                    for dep in deps:
                        for loc in dep.get('locations', []):
                            if loc:
                                file_paths.add(loc)
                    
                    manifest = DependencyInfo(
                        file_path=', '.join(sorted(file_paths)[:3]) if file_paths else f'{ecosystem} dependencies',
                        file_type='sbom',
                        ecosystem=ecosystem,
                        dependencies=[{'name': d['name'], 'version': d['version']} for d in deps],
                        build_tool='syft'
                    )
                    manifests.append(manifest)
                    total_deps += len(deps)
            
            # Create project analysis with Dockerfile adoption info
            project = ProjectAnalysis(
                repository=repo_info,
                manifests=manifests,
                total_dependencies=total_deps,
                collection_timestamp=datetime.now(timezone.utc).isoformat(),
                dockerfile_adoption=dockerfile_results if dockerfile_results['dockerfiles_found'] > 0 else None
            )
            
            return project
            
        except Exception as e:
            self.logger.error(f"Failed to analyze {repo_info.name}: {e}")
            return None
        finally:
            # Always cleanup cloned repository
            if clone_path:
                self.git_cloner.cleanup(clone_path)
    
    def _calculate_ecosystems_breakdown(self, projects: List[ProjectAnalysis]) -> Dict[str, Dict[str, Any]]:
        """Calculate ecosystems breakdown from projects."""
        ecosystems = {}
        
        for project in projects:
            for manifest in project.manifests:
                ecosystem = manifest.ecosystem
                if ecosystem not in ecosystems:
                    ecosystems[ecosystem] = {
                        'total_projects': 0,
                        'total_dependencies': 0
                    }
                
                ecosystems[ecosystem]['total_projects'] += 1
                ecosystems[ecosystem]['total_dependencies'] += len(manifest.dependencies)
        
        # Remove duplicates by counting unique projects per ecosystem
        for ecosystem in ecosystems:
            unique_projects = set()
            total_deps = 0
            
            for project in projects:
                has_ecosystem = any(m.ecosystem == ecosystem for m in project.manifests)
                if has_ecosystem:
                    unique_projects.add(project.repository.name)
                    total_deps += sum(len(m.dependencies) for m in project.manifests if m.ecosystem == ecosystem)
            
            ecosystems[ecosystem]['total_projects'] = len(unique_projects)
            ecosystems[ecosystem]['total_dependencies'] = total_deps
        
        return ecosystems
    
    def save_analysis(self, analysis: OrganizationAnalysis, output_file: str):
        """Save analysis to JSON file."""
        with open(output_file, 'w') as f:
            json.dump(asdict(analysis), f, indent=2, default=str)
        
        self.logger.info(f"Analysis saved to {output_file}")
    
    def load_analysis(self, input_file: str) -> OrganizationAnalysis:
        """Load analysis from JSON file."""
        with open(input_file, 'r') as f:
            data = json.load(f)
        
        # Convert back to dataclass instances
        projects = []
        for project_data in data.get("projects", []):
            repo_data = project_data["repository"]
            repo = RepositoryInfo(**repo_data)
            
            manifests = []
            for manifest_data in project_data.get("manifests", []):
                manifests.append(DependencyInfo(**manifest_data))
            
            projects.append(ProjectAnalysis(
                repository=repo,
                manifests=manifests,
                total_dependencies=project_data["total_dependencies"],
                collection_timestamp=project_data["collection_timestamp"],
                note=project_data.get("note", ""),
                dockerfile_adoption=project_data.get("dockerfile_adoption")
            ))

        skipped = [
            SkippedRepository(**s) for s in data.get("skipped_projects", [])
        ]

        return OrganizationAnalysis(
            organization_name=data["organization_name"],
            platform=data["platform"],
            timestamp=data["timestamp"],
            total_projects=data["total_projects"],
            analyzed_projects=data["analyzed_projects"],
            total_dependencies=data["total_dependencies"],
            projects=projects,
            ecosystems_breakdown=data["ecosystems_breakdown"],
            skipped_projects=skipped,
        )
    
    def generate_summary_report(self, analysis: OrganizationAnalysis) -> Dict[str, Any]:
        """Generate a summary report from analysis."""
        return {
            "organization": analysis.organization_name,
            "platform": analysis.platform,
            "scan_timestamp": analysis.timestamp,
            "summary": {
                "total_projects": analysis.total_projects,
                "analyzed_projects": analysis.analyzed_projects,
                "total_dependencies": analysis.total_dependencies,
            },
            "ecosystems": analysis.ecosystems_breakdown,
            "top_dependencies": self._get_top_dependencies(analysis),
            "projects_by_ecosystem": self._group_projects_by_ecosystem(analysis)
        }
    
    def _get_top_dependencies(self, analysis: OrganizationAnalysis, limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """Get top dependencies by ecosystem."""
        ecosystem_deps = {}
        
        for project in analysis.projects:
            for manifest in project.manifests:
                ecosystem = manifest.ecosystem
                if ecosystem not in ecosystem_deps:
                    ecosystem_deps[ecosystem] = {}
                
                for dep in manifest.dependencies:
                    dep_name = dep['name']
                    if dep_name not in ecosystem_deps[ecosystem]:
                        ecosystem_deps[ecosystem][dep_name] = 0
                    ecosystem_deps[ecosystem][dep_name] += 1
        
        # Sort and limit
        return {eco: sorted(list(deps)) for eco, deps in ecosystem_deps.items()}
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        return datetime.now(timezone.utc).isoformat()
    
    def _group_projects_by_ecosystem(self, analysis: OrganizationAnalysis) -> Dict[str, List[str]]:
        """Group project names by ecosystem."""
        ecosystem_projects = {}
        
        for project in analysis.projects:
            ecosystems_in_project = set(m.ecosystem for m in project.manifests)
            for ecosystem in ecosystems_in_project:
                if ecosystem not in ecosystem_projects:
                    ecosystem_projects[ecosystem] = []
                ecosystem_projects[ecosystem].append(project.repository.name)
        
        return ecosystem_projects
