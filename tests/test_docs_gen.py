"""Tests for the docs-gen CLI entry point."""
import json
from .conftest import cli


def test_help_lists_subcommands():
    result = cli("--help")
    assert result.returncode == 0
    for cmd in ["scan", "assess", "validate", "audit", "doctor", "state",
                "validate-plan", "build-registry", "generate-action"]:
        assert cmd in result.stdout


def test_version_flag():
    result = cli("--version")
    assert result.returncode == 0
    assert "docs-gen" in result.stdout


def test_unknown_subcommand_fails():
    result = cli("bogus")
    assert result.returncode == 1
    assert "Unknown subcommand" in result.stderr


def test_no_args_shows_help():
    result = cli()
    assert result.returncode == 1  # missing subcommand
    assert "Subcommands" in result.stdout


def test_scan_subcommand_works(tmp_repo, write_md):
    write_md("README.md", "# X\n")
    result = cli("scan", str(tmp_repo))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "README" in data["standard_docs"]


def test_state_subcommand_works(tmp_repo):
    result = cli("state", "init", str(tmp_repo))
    assert result.returncode == 0
    assert (tmp_repo / ".docs-meta" / "state.json").exists()
