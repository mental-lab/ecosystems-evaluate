#!/usr/bin/env python3
"""Backwards-compatible entry point — the CLI lives in repo_analyzer.cli.

When installed as a package, use the `ecosystems-evaluate` command instead.
"""

from repo_analyzer.cli import cli


if __name__ == "__main__":
    cli()
