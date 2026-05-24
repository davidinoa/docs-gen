"""Tests for scan_docs.py."""
import json
from .conftest import run_script


def test_scan_empty_repo(tmp_repo):
    """Scanning an empty repo returns empty results, no crash."""
    result = run_script("scan_docs.py", str(tmp_repo))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["standard_docs"] == {}
    assert data["other_docs"] == []


def test_scan_finds_canonical_readme(tmp_repo, write_md):
    """A README.md at root is found and marked canonical."""
    write_md("README.md", "# Project\n")
    result = run_script("scan_docs.py", str(tmp_repo))
    data = json.loads(result.stdout)
    assert "README" in data["standard_docs"]
    assert data["standard_docs"]["README"]["is_canonical_name"] is True


def test_scan_finds_non_canonical_spec(tmp_repo, write_md):
    """PRD.md is detected as SPECS but flagged non-canonical."""
    write_md("PRD.md", "# Product Requirements\n\nLong content here.\n")
    result = run_script("scan_docs.py", str(tmp_repo))
    data = json.loads(result.stdout)
    assert "SPECS" in data["standard_docs"]
    assert data["standard_docs"]["SPECS"]["found_at"] == "PRD.md"
    assert data["standard_docs"]["SPECS"]["is_canonical_name"] is False


def test_scan_categorizes_other_docs(tmp_repo, write_md):
    """Non-standard .md files go to other_docs."""
    write_md("CONTEXT.md", "# Context\n")
    write_md("PERSONAS.md", "# Personas\n")
    result = run_script("scan_docs.py", str(tmp_repo))
    data = json.loads(result.stdout)
    other_paths = {d["path"] for d in data["other_docs"]}
    assert "CONTEXT.md" in other_paths
    assert "PERSONAS.md" in other_paths


def test_scan_skips_health_system_files(tmp_repo, write_md):
    """DOCS_REGISTRY.md and DOCS_AUDIT_LOG.md aren't reported as other docs."""
    write_md("DOCS_REGISTRY.md", "# Registry\n")
    write_md("DOCS_AUDIT_LOG.md", "# Audit\n")
    result = run_script("scan_docs.py", str(tmp_repo))
    data = json.loads(result.stdout)
    other_paths = {d["path"] for d in data["other_docs"]}
    assert "DOCS_REGISTRY.md" not in other_paths
    assert "DOCS_AUDIT_LOG.md" not in other_paths


def test_scan_finds_doc_in_subdir(tmp_repo, write_md):
    """Architecture doc in docs/ subdir is found, flagged non-canonical."""
    write_md("docs/architecture.md", "# Architecture\n")
    result = run_script("scan_docs.py", str(tmp_repo))
    data = json.loads(result.stdout)
    assert "ARCHITECTURE" in data["standard_docs"]
    assert data["standard_docs"]["ARCHITECTURE"]["found_at"] == "docs/architecture.md"
    assert data["standard_docs"]["ARCHITECTURE"]["is_canonical_name"] is False


def test_scan_detects_health_system(tmp_repo, write_md):
    """Existing registry/audit/action are detected."""
    write_md("DOCS_REGISTRY.md", "# Registry\n")
    write_md("DOCS_AUDIT_LOG.md", "# Audit\n")
    write_md(".github/workflows/docs-check.yml", "name: Docs Check\n")
    result = run_script("scan_docs.py", str(tmp_repo))
    data = json.loads(result.stdout)
    assert data["health_system"]["registry_exists"] is True
    assert data["health_system"]["audit_log_exists"] is True
    assert data["health_system"]["docs_check_action_exists"] is True


def test_scan_stdout_is_pure_json(tmp_repo):
    """Status messages must not leak into stdout — JSON must parse cleanly."""
    result = run_script("scan_docs.py", str(tmp_repo))
    assert result.returncode == 0
    # If stderr was leaking into stdout, json.loads would throw
    data = json.loads(result.stdout)
    assert "standard_docs" in data
