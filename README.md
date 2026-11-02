# Ecosystems Evaluate

Dependency and container image analysis for GitLab, GitHub, and Azure DevOps.

## Quick Start (Container — recommended)

The image is self-contained (includes git and syft) and runs as nonroot on a
Chainguard base.

```bash
# Configure credentials (copy .env.example from the repo, or create your own)
# PLATFORM=github  SOURCE=https://github.com  TOKEN=...  ORG=my-org
docker run --rm --env-file .env -v "$PWD:/out" \
  ghcr.io/mental-lab/ecosystems-evaluate:latest \
  -O /out/analysis.json -v
```

Build locally instead of pulling:

```bash
git clone https://github.com/mental-lab/ecosystems-evaluate.git
cd ecosystems-evaluate
cp .env.example .env   # fill in your values
make docker-run        # builds the image, runs analysis, writes ./analysis.json
```

`.env` and other secrets are excluded from the image build via `.dockerignore`.

## Quick Start (CLI)

Requires Python 3.10+, git 2.31+, and
[syft](https://github.com/anchore/syft) (`brew install syft`) on PATH.

```bash
pipx install git+https://github.com/mental-lab/ecosystems-evaluate.git

# Configure credentials (recommended — .env is gitignored)
cp .env.example .env   # from a clone, or create one with PLATFORM/SOURCE/TOKEN/ORG

ecosystems-evaluate -O analysis.json -v
```

## Local Development

```bash
git clone https://github.com/mental-lab/ecosystems-evaluate.git
cd ecosystems-evaluate
make install     # venv + pip install -e .
make test        # run the test suite
python3 main.py -O analysis.json -v   # or: ecosystems-evaluate -O analysis.json -v
```

## Supported Platforms

- **GitLab** - gitlab.com or self-hosted
- **GitHub** - github.com or Enterprise
- **Azure DevOps** - dev.azure.com or Server

## What Gets Detected

- All ecosystems: Python, Java, JavaScript, Go, Rust, Ruby, .NET, Swift, Elixir, PHP, and more
- Dockerfile base images and Chainguard adoption
- GitHub Actions and workflows

## Output

```
Projects analyzed: 14/18
Total dependencies: 9,219

Dockerfile Adoption:
   Repos with Dockerfiles: 10/14
   Repos using Chainguard: 6/10
```

## Options

Run `ecosystems-evaluate --help` (or `python3 main.py --help`) for all options.
- `-p, --platform` - Platform: gitlab, github, ado
- `-s, --source` - Platform instance URL
- `-t, --token` - Personal access token (prefer `TOKEN` env var or `.env` — CLI tokens leak via shell history)
- `-o, --org` - Organization/group name
- `-r, --repo` - Specific repository (optional)
- `-b, --branch` - Specific branch to analyze (default: repository default branch)
- `-O, --output` - Output file path
- `-w, --workers` - Parallel workers (default: 4)
- `-v, --verbose` - Show progress

Environment variables: `PLATFORM`, `SOURCE`, `TOKEN`, `ORG`, `WORKERS`,
`REQUEST_TIMEOUT` (API timeout in seconds, default 60).

## Examples

See [examples/README.md](examples/README.md) for more usage examples.

## Getting Tokens

- **GitLab**: Settings → Access Tokens → `read_api` + `read_repository`
- **GitHub**: Settings → Developer settings → PAT → `repo` scope
- **Azure DevOps**: User settings → PAT → `Code (read)` scope

## Troubleshooting

**`syft is not installed or not available in PATH`** — install syft
(`brew install syft` or see the [syft docs](https://github.com/anchore/syft)),
or use the container image which bundles it. Same for `git`.

**401 authentication failed** — the token is invalid or expired; create a new
one with the scopes above.

**403 permission denied** — the token lacks the required scopes, or the account
cannot see the organization (SSO enforcement on GitHub also requires
authorizing the PAT for the org).

**404 not found** — check the `ORG` name and `SOURCE` URL. For Azure DevOps
the org is part of the URL (`https://dev.azure.com/<org>`).

**Rate limiting / timeouts** — the tool paces API requests automatically and
backs off when limits are near. For slow self-hosted instances raise
`REQUEST_TIMEOUT` (e.g. `REQUEST_TIMEOUT=120`).

**`Permission denied` writing to `/out` (container)** — mount a directory
under your home folder (e.g. `-v "$PWD:/out"`). Some Docker runtimes
(Rancher Desktop) restrict writes to bind mounts outside the home directory.

## Releasing (maintainers)

Tag a commit to publish the container image to GHCR:

```bash
git tag v1.0.1 && git push --tags
```

CI builds, scans (grype, fails on high), and pushes
`ghcr.io/mental-lab/ecosystems-evaluate:<tag>` and `:latest`. After the first
push, set the package to public in GitHub package settings so customers can
pull without auth.
