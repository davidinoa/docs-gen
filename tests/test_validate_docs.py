"""Tests for validate_docs.py."""
import json
from .conftest import run_script


def test_validate_no_issues_on_clean_docs(tmp_repo, write_md):
    write_md("README.md", "# Project\n\nClean and simple.\n")
    write_md("ARCHITECTURE.md", "# Arch\n\nNothing controversial here.\n")
    result = run_script("validate_docs.py",
                        str(tmp_repo / "README.md"),
                        str(tmp_repo / "ARCHITECTURE.md"),
                        "--output", str(tmp_repo / "report.json"))
    assert result.returncode == 0
    report = json.loads((tmp_repo / "report.json").read_text())
    assert report["summary"]["high"] == 0


def test_validate_detects_version_conflict(tmp_repo, write_md):
    write_md("README.md", "Requires Node.js 18 for development.\n")
    write_md("ARCHITECTURE.md", "Built on Node.js 20 runtime.\n")
    result = run_script("validate_docs.py",
                        str(tmp_repo / "README.md"),
                        str(tmp_repo / "ARCHITECTURE.md"),
                        "--output", str(tmp_repo / "report.json"))
    assert result.returncode == 2  # high-severity exit
    report = json.loads((tmp_repo / "report.json").read_text())
    version_issues = [i for i in report["issues"] if i["type"] == "version_conflict"]
    assert len(version_issues) >= 1
    assert version_issues[0]["technology"] == "Node.js"


def test_validate_detects_db_claim_conflict(tmp_repo, write_md):
    write_md("ARCHITECTURE.md", "We use PostgreSQL for persistence.\n")
    write_md("DATA_MODEL.md", "Our MongoDB collections store records.\n")
    result = run_script("validate_docs.py",
                        str(tmp_repo / "ARCHITECTURE.md"),
                        str(tmp_repo / "DATA_MODEL.md"),
                        "--output", str(tmp_repo / "report.json"))
    report = json.loads((tmp_repo / "report.json").read_text())
    claim_issues = [i for i in report["issues"] if i["type"] == "claim_conflict"]
    db_issues = [i for i in claim_issues if i["category"] == "database"]
    assert len(db_issues) == 1


def test_validate_dominant_value_suppresses_false_positive(tmp_repo, write_md):
    """A doc that mentions NX 7 times and Turborepo once should NOT conflict with another doc that uses NX."""
    write_md("ARCHITECTURE.md", """
We use NX for the monorepo. NX gives us affected-graph builds. NX caches per package.
NX is mandated by the org. We considered Turborepo but chose NX for team familiarity.
NX is our standard. With NX, build orchestration is consistent.
""")
    write_md("MONOREPO.md", "Workspace is NX-managed. NX runs all tasks.\n")
    result = run_script("validate_docs.py",
                        str(tmp_repo / "ARCHITECTURE.md"),
                        str(tmp_repo / "MONOREPO.md"),
                        "--output", str(tmp_repo / "report.json"))
    report = json.loads((tmp_repo / "report.json").read_text())
    claim_issues = [i for i in report["issues"] if i["type"] == "claim_conflict"]
    monorepo_issues = [i for i in claim_issues if i["category"] == "monorepo_tool"]
    assert len(monorepo_issues) == 0  # Suppressed because NX dominates in both


def test_validate_real_conflict_not_suppressed(tmp_repo, write_md):
    """When two docs disagree on the dominant value, conflict IS flagged."""
    write_md("ARCHITECTURE.md", "We use Clerk for auth. Clerk handles sessions. Clerk is configured via env vars.\n")
    write_md("RUNBOOK.md", "Auth is via Auth0. Auth0 tokens. Auth0 admin panel.\n")
    result = run_script("validate_docs.py",
                        str(tmp_repo / "ARCHITECTURE.md"),
                        str(tmp_repo / "RUNBOOK.md"),
                        "--output", str(tmp_repo / "report.json"))
    report = json.loads((tmp_repo / "report.json").read_text())
    auth_conflicts = [i for i in report["issues"]
                      if i["type"] == "claim_conflict" and i["category"] == "auth_provider"]
    assert len(auth_conflicts) == 1


def test_validate_extracts_claims_per_doc(tmp_repo, write_md):
    write_md("README.md", "Built with Next.js, React, and PostgreSQL. Deployed to Vercel.\n")
    result = run_script("validate_docs.py",
                        str(tmp_repo / "README.md"),
                        "--output", str(tmp_repo / "report.json"))
    report = json.loads((tmp_repo / "report.json").read_text())
    claims = report["extracted_claims"]["README.md"]
    assert "database" in claims
    assert claims["database"]["dominant"] == "PostgreSQL"
    assert "deploy_target" in claims
    assert claims["deploy_target"]["all_mentioned"].get("Vercel", 0) >= 1


def test_validate_handles_no_docs_gracefully(tmp_repo):
    result = run_script("validate_docs.py", str(tmp_repo / "nonexistent.md"))
    assert result.returncode == 1  # No readable docs
