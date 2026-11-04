"""Command-line interface for Ecosystems Evaluate.

Analysis runs locally: repositories are cloned with git, scanned with syft,
and results written to a JSON report. Credentials come from CLI flags,
environment variables, or a .env file.
"""

import json
import logging
import os
import time
from dataclasses import asdict

import click
import requests
from dotenv import find_dotenv, load_dotenv

from . import __version__
from .repository_analyzer import RepositoryAnalyzer


@click.command()
@click.version_option(__version__)
@click.option('-p', '--platform', type=click.Choice(['gitlab', 'github', 'ado', 'local'], case_sensitive=False), help='Platform to analyze (gitlab, github, ado, local)')
@click.option('-s', '--source', help='Platform instance URL, or directory path for local analysis')
@click.option('-t', '--token', help='Personal access token')
@click.option('-o', '--org', help='Organization/group name to analyze')
@click.option('-r', '--repo', help='Specific repository to analyze (format: owner/repo for GitHub, group/project for GitLab)')
@click.option('-b', '--branch', help='Specific branch to analyze (default: repository default branch)')
@click.option('-O', '--output', required=True, help='Output JSON file for analysis')
@click.option('-w', '--workers', type=int, default=None, help='Number of parallel workers (default: 4, or WORKERS env var)')
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
def cli(platform: str, source: str, token: str, org: str, repo: str, branch: str, output: str, workers: int, verbose: bool):
    """Analyze organization or repository for dependency inventory.

    Platforms:
        gitlab  - Fully tested
        github  - Fully tested
        ado     - Azure DevOps support
        local   - Existing directory, no credentials required

    Examples:
        # Using environment variables (recommended - see .env.example)
        ecosystems-evaluate -O analysis.json -v

        # Using CLI flags
        ecosystems-evaluate -p gitlab -s https://gitlab.com -t $TOKEN -o mygroup -O analysis.json -v

        # Analyze specific repository
        ecosystems-evaluate -p github -s https://github.com -o myorg -r owner/repo -O analysis.json

        # Analyze specific branch
        ecosystems-evaluate -p github -s https://github.com -o myorg -b develop -O analysis.json
    """
    start_time = time.time()

    # Progress and error logs are suppressed by default so the summary stays
    # readable; -v surfaces per-repo progress on stderr
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format='%(levelname)s %(name)s: %(message)s'
    )

    # Load .env file if present, searching from the working directory
    # upward (values are overridden by real env vars)
    load_dotenv(find_dotenv(usecwd=True))

    # Warn if the token is passed on the command line — it ends up in
    # shell history and is visible in the process list while running
    if token:
        click.echo(
            "Warning: passing -t/--token exposes it in shell history and the "
            "process list. Prefer the TOKEN env var or a .env file.",
            err=True
        )

    # Load from environment variables if not provided via CLI
    # Priority: CLI flags > Environment variables > .env file > Defaults
    platform = platform or os.getenv('PLATFORM')
    source = source or os.getenv('SOURCE')
    token = token or os.getenv('TOKEN')
    org = org or os.getenv('ORG')
    if workers is None:
        workers = int(os.getenv('WORKERS', '4'))

    platform = platform.lower() if platform else platform
    if platform == 'local':
        if not source:
            raise click.UsageError("--source is required for local analysis")
        if repo or branch:
            raise click.UsageError("--repo and --branch are not supported for local analysis; scan the current checkout")
        source = click.Path(exists=True, file_okay=False, readable=True, resolve_path=True).convert(
            os.path.expanduser(source), None, None
        )
        # Local scans never use credentials loaded from the environment.
        token = None
        org = None

    # Validate required parameters
    if platform != 'local' and not all([platform, source, token, org]):
        click.echo("Error: -p/--platform, -s/--source, -t/--token, and -o/--org are required", err=True)
        click.echo("Tip: set PLATFORM, SOURCE, TOKEN, and ORG in a .env file instead", err=True)
        raise click.Abort()

    if workers < 1:
        click.echo("Error: --workers must be at least 1", err=True)
        raise click.Abort()

    try:
        # Initialize analyzer with platform credentials
        analyzer = RepositoryAnalyzer(platform=platform, url=source, token=token, max_workers=workers)

        if platform == 'local':
            if verbose:
                click.echo(f"Analyzing local directory {source}")
            analysis = analyzer.analyze_local(source)
        elif repo:
            # Analyze specific repository
            # For GitHub, need to combine org/repo format
            if platform.lower() == 'github' and '/' not in repo:
                repo_spec = f"{org}/{repo}"
            else:
                repo_spec = repo

            if verbose:
                branch_msg = f" (branch: {branch})" if branch else ""
                click.echo(f"Analyzing repository {repo_spec} on {platform}{branch_msg}")
            analysis = analyzer.analyze_repository(repo_spec, branch=branch)
        else:
            # Analyze entire organization
            if verbose:
                branch_msg = f" (branch: {branch})" if branch else ""
                click.echo(f"Analyzing {org} organization on {platform}{branch_msg}")
                click.echo(f"Using {workers} parallel workers")

            analysis = analyzer.analyze_organization(org, branch=branch)

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        hints = {
            401: "authentication failed — check that your TOKEN is valid and not expired",
            403: "permission denied — check token scopes (see README 'Getting Tokens') and org access",
            404: "not found — check the ORG name and SOURCE URL",
        }
        click.echo(f"Analysis failed: {e}", err=True)
        if status in hints:
            click.echo(f"Hint ({status}): {hints[status]}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Analysis failed: {e}", err=True)
        raise click.Abort()

    # Save results
    output_dir = os.path.dirname(output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output, 'w') as f:
        json.dump(asdict(analysis), f, indent=2, default=str)

    if verbose:
        click.echo("\nAnalysis Complete:")
        if repo:
            click.echo(f"   Repository: {repo}")
            click.echo(f"   Total dependencies: {analysis.total_dependencies}")
        else:
            click.echo(f"   Projects analyzed: {analysis.analyzed_projects}/{analysis.total_projects}")
            click.echo(f"   Total dependencies: {analysis.total_dependencies}")

            # Show skipped projects summary
            if analysis.skipped_projects:
                click.echo(f"\n   Skipped projects: {len(analysis.skipped_projects)}")

                # Group by reason
                skip_reasons = {}
                for skipped in analysis.skipped_projects:
                    reason = skipped.reason
                    if reason not in skip_reasons:
                        skip_reasons[reason] = []
                    skip_reasons[reason].append(skipped.name)

                for reason, repos in skip_reasons.items():
                    click.echo(f"      {reason}: {len(repos)}")
                    for name in repos:
                        click.echo(f"         - {name}")

            # Show ecosystem breakdown
            click.echo("")
            for eco, data in analysis.ecosystems_breakdown.items():
                click.echo(f"   {eco.upper()}: {data['total_dependencies']} deps ({data['total_projects']} projects)")

        # Show Dockerfile adoption summary
        repos_with_dockerfiles = 0
        repos_with_chainguard_images = 0
        total_chainguard_images = []

        for project in analysis.projects:
            if project.dockerfile_adoption:
                repos_with_dockerfiles += 1
                if project.dockerfile_adoption.get('adoption_detected'):
                    repos_with_chainguard_images += 1
                    total_chainguard_images.extend(project.dockerfile_adoption.get('chainguard_images', []))

        if repos_with_dockerfiles > 0:
            click.echo("\nDockerfile Adoption:")
            click.echo(f"   Repos with Dockerfiles: {repos_with_dockerfiles}/{len(analysis.projects)}")
            click.echo(f"   Repos using Chainguard: {repos_with_chainguard_images}/{repos_with_dockerfiles}")
            if repos_with_chainguard_images > 0:
                click.echo(f"   Total Chainguard images: {len(total_chainguard_images)}")

    click.echo(f"Report saved to: {output}")

    elapsed = time.time() - start_time
    if verbose:
        click.echo(f"Completed in {elapsed:.2f}s")
