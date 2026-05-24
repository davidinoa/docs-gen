"""Tests for the `template` subcommand."""
from pathlib import Path

from .conftest import cli


def test_template_list_shows_packaged_files():
    result = cli("template", "list")
    assert result.returncode == 0
    assert "doc-templates.md" in result.stdout
    assert "adr-format.md" in result.stdout
    assert "workflows/docs-health.yml" in result.stdout


def test_template_show_prints_packaged_template():
    result = cli("template", "show", "adr-format.md")
    assert result.returncode == 0
    # adr-format.md is a markdown ADR template — content starts with a heading.
    assert result.stdout.startswith("#") or "ADR" in result.stdout


def test_template_show_unknown_returns_error():
    result = cli("template", "show", "does-not-exist.md")
    assert result.returncode == 1


def test_template_show_respects_override_dir(tmp_repo):
    custom = tmp_repo / "tmpl"
    custom.mkdir()
    (custom / "adr-format.md").write_text("custom adr override")
    result = cli("template", "--template-dir", str(custom),
                 "show", "adr-format.md")
    assert result.returncode == 0
    assert result.stdout == "custom adr override"


def test_template_list_marks_overrides(tmp_repo):
    custom = tmp_repo / "tmpl"
    custom.mkdir()
    (custom / "adr-format.md").write_text("x")
    result = cli("template", "--template-dir", str(custom), "list")
    assert result.returncode == 0
    # adr-format.md should be marked as override, others as packaged.
    lines = {line.split("\t")[0]: line.split("\t")[1] for line in result.stdout.strip().splitlines() if "\t" in line}
    assert "(override)" in lines["adr-format.md"]
    assert "(packaged)" in lines["doc-templates.md"]


def test_template_missing_override_dir_errors(tmp_repo):
    missing = tmp_repo / "nope"
    result = cli("template", "--template-dir", str(missing), "list")
    assert result.returncode == 1
