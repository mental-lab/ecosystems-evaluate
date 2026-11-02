# Examples

See [`sample_output.json`](./sample_output.json) for example output format.

## Container (recommended)

```bash
# .env holds PLATFORM/SOURCE/TOKEN/ORG
docker run --rm --env-file .env -v "$PWD:/out" \
  ghcr.io/mental-lab/ecosystems-evaluate:latest \
  -O /out/analysis.json -v
```

## CLI (installed via pipx)

### Using .env file (Recommended)

```bash
# 1. Configure .env
PLATFORM=gitlab
SOURCE=https://gitlab.com
TOKEN=glpat-xxx
ORG=my-org

# 2. Run
ecosystems-evaluate -O analysis.json -v
```

### Using CLI flags

```bash
# GitLab
ecosystems-evaluate -p gitlab -s https://gitlab.com -t $TOKEN -o my-org -O analysis.json -v

# GitHub
ecosystems-evaluate -p github -s https://github.com -t $TOKEN -o my-org -O analysis.json -v

# Azure DevOps
ecosystems-evaluate -p ado -s https://dev.azure.com/my-org -t $TOKEN -o my-org -O analysis.json -v
```

Running from a source checkout? Substitute `python3 main.py` for
`ecosystems-evaluate` in any of these commands.

## Advanced

```bash
# Specific repository
ecosystems-evaluate -p github -t $TOKEN -o my-org -r owner/repo -O analysis.json -v

# Specific branch
ecosystems-evaluate -p github -t $TOKEN -o my-org -b develop -O analysis.json -v

# More workers for large orgs
ecosystems-evaluate -O analysis.json -w 8 -v

# Longer API timeout for slow self-hosted instances
REQUEST_TIMEOUT=120 ecosystems-evaluate -O analysis.json -v
```
