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


def test_quiet_suppresses_status_messages(tmp_repo, write_md):
    """--quiet should silence status output but keep stdout intact."""
    write_md("README.md", "# X\n")
    result = cli("--quiet", "scan", str(tmp_repo))
    assert result.returncode == 0
    # JSON output still on stdout
    json.loads(result.stdout)
    # Status messages absent from stderr
    assert "Scanning" not in result.stderr
    assert "Loading doc types" not in result.stderr


def test_log_format_json_emits_structured_events(tmp_repo, write_md):
    """--log-format=json should turn status messages into JSON objects on stderr."""
    write_md("README.md", "# X\n")
    result = cli("--log-format=json", "scan", str(tmp_repo))
    assert result.returncode == 0
    # Each non-empty stderr line should parse as JSON.
    for line in (l for l in result.stderr.splitlines() if l.strip()):
        event = json.loads(line)
        assert "level" in event
        assert "message" in event


def test_verbose_does_not_break_normal_output(tmp_repo, write_md):
    write_md("README.md", "# X\n")
    result = cli("--verbose", "scan", str(tmp_repo))
    assert result.returncode == 0
    json.loads(result.stdout)


def test_template_subcommand_listed_in_help():
    result = cli("--help")
    assert "template" in result.stdout
