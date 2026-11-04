# Ecosystems Evaluate

[![CI](https://github.com/mental-lab/ecosystems-evaluate/actions/workflows/ci.yml/badge.svg)](https://github.com/mental-lab/ecosystems-evaluate/actions/workflows/ci.yml)

Dependency and container image analysis for GitLab, GitHub, Azure DevOps, and
local repository checkouts.

Already have the repository on disk? Use
[local checkout analysis](#analyze-a-local-checkout) without credentials or cloning.

## Quick Start (Container — recommended)

The image is self-contained (includes git and syft) and runs as nonroot on a
Chainguard base. The following command is for macOS/Linux. For Windows, use
the Git Bash or PowerShell command below.

```bash
# Configure credentials (copy .env.example from the repo, or create your own)
# PLATFORM=github  SOURCE=https://github.com  TOKEN=...  ORG=my-org
docker run --rm --env-file .env -v "$PWD:/out" \
  ghcr.io/mental-lab/ecosystems-evaluate:latest \
  -O /out/analysis.json -v
```

Windows Git Bash:

```bash
MSYS_NO_PATHCONV=1 docker run --rm --env-file .env \
  --mount "type=bind,source=$(pwd -W),target=/out" \
  ghcr.io/mental-lab/ecosystems-evaluate:latest \
  -O /out/analysis.json -v
```

Windows PowerShell:

```powershell
docker run --rm --env-file .env --mount "type=bind,source=${PWD},target=/out" `
  ghcr.io/mental-lab/ecosystems-evaluate:latest `
  -O /out/analysis.json -v
```

After a successful run, `analysis.json` is in the host directory where you ran
the command. `/out` is the mounted directory inside the container.

Build locally instead of pulling:

```bash
git clone https://github.com/mental-lab/ecosystems-evaluate.git
cd ecosystems-evaluate
cp .env.example .env   # fill in your values
make docker-run        # builds the image, runs analysis, writes ./analysis.json
```

`.env` and other secrets are excluded from the image build via `.dockerignore`.

## Quick Start (CLI)

Requires Python 3.10+ and
[syft](https://github.com/anchore/syft) (`brew install syft`) on PATH.
Remote analysis also requires git 2.31+.

```bash
pipx install git+https://github.com/mental-lab/ecosystems-evaluate.git

# Scan an existing local checkout (no credentials)
ecosystems-evaluate -p local -s ./my-repo -O analysis.json -v
```

For GitLab, GitHub, or Azure DevOps, configure credentials first:

```bash
# .env is gitignored
cp .env.example .env   # from a clone, or create one with PLATFORM/SOURCE/TOKEN/ORG

ecosystems-evaluate -O analysis.json -v
```

## Analyze a Local Checkout

Scan a repository already on your filesystem without a token, organization,
API requests, or cloning:

```bash
ecosystems-evaluate -p local -s ./my-repo -O analysis.json -v
# From a source checkout:
python3 main.py -p local -s ./my-repo -O analysis.json -v
```

This scans the files currently on disk, including uncommitted changes, using
Syft and the Dockerfile scanner. The directory does not need Git metadata.
Syft must be installed for CLI usage; git is only required for remote scans.
`--repo` and `--branch` are unavailable in local mode. Existing TOKEN and ORG
values in your environment or `.env` are ignored for local analysis.

Container (macOS/Linux), with the checkout mounted read-only:

```bash
docker run --rm \
  --mount "type=bind,source=$PWD/my-repo,target=/repo,readonly" \
  --mount "type=bind,source=$PWD,target=/out" \
  ghcr.io/mental-lab/ecosystems-evaluate:latest \
  -p local -s /repo -O /out/analysis.json -v
```

Windows Git Bash:

```bash
MSYS_NO_PATHCONV=1 docker run --rm \
  --mount "type=bind,source=$(pwd -W)/my-repo,target=/repo,readonly" \
  --mount "type=bind,source=$(pwd -W),target=/out" \
  ghcr.io/mental-lab/ecosystems-evaluate:latest \
  -p local -s /repo -O /out/analysis.json -v
```

Windows PowerShell:

```powershell
docker run --rm `
  --mount "type=bind,source=${PWD}/my-repo,target=/repo,readonly" `
  --mount "type=bind,source=${PWD},target=/out" `
  ghcr.io/mental-lab/ecosystems-evaluate:latest `
  -p local -s /repo -O /out/analysis.json -v
```

Replace `my-repo` with your checkout directory. These container commands need
no `.env` file and write `analysis.json` to the current host directory. Use an
image built from this change (or the published image after release).

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
- **Local** - An existing directory on your filesystem

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
- `-p, --platform` - Platform: gitlab, github, ado, local
- `-s, --source` - Platform instance URL, or directory path for local analysis
- `-t, --token` - Personal access token for remote analysis (prefer `TOKEN` env var or `.env` — CLI tokens leak via shell history)
- `-o, --org` - Organization/group name for remote analysis
- `-r, --repo` - Specific remote repository (optional)
- `-b, --branch` - Remote branch to analyze (default: repository default branch); local mode scans the current files
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

**Windows Git Bash reports a path such as
`C:/Users/.../AppData/Local/Git/out/analysis.json`, but no host file exists** —
Git Bash can rewrite the container argument `/out/analysis.json` into a Windows
path before Docker receives it. The analyzer may write that path inside the
container, outside the bind mount; `--rm` then deletes it with the container.
Changing the host directory alone does not fix this. Use the Git Bash command
in Quick Start: `MSYS_NO_PATHCONV=1` preserves container paths, while
`$(pwd -W)` supplies a native Windows path for the host mount. Rerun the analysis
and check `ls -l analysis.json` in the host directory, or use PowerShell.
See [Docker's Git Bash troubleshooting](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/topics/#docker-commands-failing-in-git-bash).

## Releasing (maintainers)

Tag a commit to publish the container image to GHCR:

```bash
git tag v1.0.1 && git push --tags
```

CI builds, scans (grype, fails on high), and pushes
`ghcr.io/mental-lab/ecosystems-evaluate:<tag>` and `:latest`. After the first
push, set the package to public in GitHub package settings so customers can
pull without auth.
