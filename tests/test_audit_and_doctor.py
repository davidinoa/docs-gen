"""Tests for append_audit.py and doctor.py."""
import json
import subprocess
from datetime import date, timedelta

import yaml
from .conftest import run_script


# ── append_audit.py ────────────────────────────────────────────────────────

def test_init_creates_audit_log(tmp_repo):
    log_path = tmp_repo / "DOCS_AUDIT_LOG.md"
    result = run_script("append_audit.py", "--log", str(log_path), "--init")
    assert result.returncode == 0
    assert log_path.exists()
    content = log_path.read_text()
    assert "# Docs Audit Log" in content
    assert "| Date | Doc(s) | Change | Trigger | Reviewer |" in content


def test_init_refuses_overwrite(tmp_repo):
    log_path = tmp_repo / "DOCS_AUDIT_LOG.md"
    run_script("append_audit.py", "--log", str(log_path), "--init")
    result = run_script("append_audit.py", "--log", str(log_path), "--init")
    assert result.returncode == 1


def test_append_adds_row(tmp_repo):
    log_path = tmp_repo / "DOCS_AUDIT_LOG.md"
    run_script("append_audit.py", "--log", str(log_path), "--init")
    result = run_script("append_audit.py", "--log", str(log_path),
                        "--docs", "README.md",
                        "--change", "Updated install steps",
                        "--trigger", "PR #99",
                        "--reviewer", "alice")
    assert result.returncode == 0
    content = log_path.read_text()
    assert "README.md" in content
    assert "Updated install steps" in content
    assert "PR #99" in content
    assert "alice" in content


def test_append_to_missing_log_creates_it(tmp_repo):
    """Appending to a non-existent log should auto-create it."""
    log_path = tmp_repo / "DOCS_AUDIT_LOG.md"
    result = run_script("append_audit.py", "--log", str(log_path),
                        "--docs", "X.md", "--change", "Y", "--trigger", "Z", "--reviewer", "W")
    assert result.returncode == 0
    assert log_path.exists()


def test_append_requires_all_fields(tmp_repo):
    log_path = tmp_repo / "DOCS_AUDIT_LOG.md"
    run_script("append_audit.py", "--log", str(log_path), "--init")
    result = run_script("append_audit.py", "--log", str(log_path), "--docs", "X.md")
    assert result.returncode == 1
    assert "Missing required arguments" in result.stderr


# ── doctor.py ─────────────────────────────────────────────────────────────

def _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan):
    """Helper: produce a complete, healthy docs ecosystem in tmp_repo."""
    write_md("README.md", "# Project\n")
    write_md("ARCHITECTURE.md", "# Architecture\n")
    write_md("package.json", '{"name": "test"}')
    write_md("src/main.js", "// stub")
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    out_dir = tmp_repo / ".github" / "workflows"
    out_dir.mkdir(parents=True)
    run_script("generate_action.py", str(tmp_repo / "docs-registry.yaml"), str(out_dir))
    run_script("append_audit.py", "--log", str(tmp_repo / "DOCS_AUDIT_LOG.md"), "--init")


def test_doctor_healthy_ecosystem(tmp_repo, write_md, write_doc_plan):
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    result = run_script("doctor.py", str(tmp_repo))
    assert result.returncode == 0


def test_doctor_no_registry_is_critical(tmp_repo):
    result = run_script("doctor.py", str(tmp_repo))
    assert result.returncode == 2  # critical


def test_doctor_detects_missing_registered_doc(tmp_repo, write_md, write_doc_plan):
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    (tmp_repo / "ARCHITECTURE.md").unlink()  # Registered but now missing
    result = run_script("doctor.py", str(tmp_repo))
    assert result.returncode == 1
    assert "ARCHITECTURE.md" in result.stdout


def test_doctor_detects_unregistered_doc(tmp_repo, write_md, write_doc_plan):
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    write_md("STRAY.md", "# Stray doc\n")
    result = run_script("doctor.py", str(tmp_repo))
    assert result.returncode == 1
    assert "STRAY.md" in result.stdout


def test_doctor_detects_stale_path(tmp_repo, write_md, write_doc_plan):
    """A path in the registry that doesn't exist in the repo is flagged."""
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    (tmp_repo / "package.json").unlink()  # Registered as README path
    result = run_script("doctor.py", str(tmp_repo))
    assert result.returncode == 1
    assert "package.json" in result.stdout


def test_audit_init_dry_run(tmp_repo):
    log_path = tmp_repo / "DOCS_AUDIT_LOG.md"
    result = run_script("append_audit.py", "--log", str(log_path), "--init", "--dry-run")
    assert result.returncode == 0
    assert not log_path.exists()


def test_audit_append_dry_run(tmp_repo):
    log_path = tmp_repo / "DOCS_AUDIT_LOG.md"
    run_script("append_audit.py", "--log", str(log_path), "--init")
    pre = log_path.read_text()
    result = run_script("append_audit.py", "--log", str(log_path), "--dry-run",
                        "--docs", "X.md", "--change", "test", "--trigger", "test", "--reviewer", "w")
    assert result.returncode == 0
    assert log_path.read_text() == pre  # No changes written


def test_doctor_full_healthy_passes(tmp_repo, write_md, write_doc_plan):
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    result = run_script("doctor.py", str(tmp_repo), "--full")
    assert result.returncode == 0


def test_doctor_full_detects_claim_conflict(tmp_repo, write_md, write_doc_plan):
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    # Inject conflicting database claims into two docs.
    (tmp_repo / "ARCHITECTURE.md").write_text(
        "# Architecture\n\n"
        "We use Postgres. Postgres. Postgres. The Postgres database is our backbone.\n"
    )
    (tmp_repo / "DATA_MODEL.md").write_text(
        "# Data Model\n\n"
        "We use MongoDB. MongoDB. MongoDB. The MongoDB schema lives in collections.\n"
    )
    # Enroll DATA_MODEL.md so doctor's structural check doesn't fail first.
    reg = yaml.safe_load((tmp_repo / "docs-registry.yaml").read_text())
    reg["docs"].append({
        "file": "DATA_MODEL.md",
        "owns": ["data model"],
        "paths": [],
        "origin": "generated",
        "cadence": "on-change",
        "custom": False,
        "last_reviewed": str(date.today()),
        "reviewer": "",
    })
    (tmp_repo / "docs-registry.yaml").write_text(yaml.safe_dump(reg, sort_keys=False))
    result = run_script("doctor.py", str(tmp_repo), "--full")
    # Content validation high-severity rolls into issues → exit 1
    assert result.returncode == 1
    assert "claim_conflict" in result.stdout or "Conflicting" in result.stdout


def test_doctor_full_no_docs_to_validate_skips_cleanly(tmp_repo, write_doc_plan):
    """If the repo has no validatable docs, --full should not crash."""
    plan_path = write_doc_plan({"docs": []})
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    run_script("append_audit.py", "--log", str(tmp_repo / "DOCS_AUDIT_LOG.md"), "--init")
    out_dir = tmp_repo / ".github" / "workflows"
    out_dir.mkdir(parents=True)
    run_script("generate_action.py", str(tmp_repo / "docs-registry.yaml"), str(out_dir))
    result = run_script("doctor.py", str(tmp_repo), "--full", "--json")
    report = json.loads(result.stdout)
    assert report["content_validation"]["ran"] is False


def test_doctor_detects_stale_docs(tmp_repo, write_md, write_doc_plan):
    """A registry entry with cadence=quarterly past the threshold is flagged."""
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    reg = yaml.safe_load((tmp_repo / "docs-registry.yaml").read_text())
    # Force one doc to be stale: quarterly cadence + last_reviewed 200 days ago
    for d in reg["docs"]:
        if d["file"] == "ARCHITECTURE.md":
            d["cadence"] = "quarterly"
            d["last_reviewed"] = str(date.today() - timedelta(days=200))
    (tmp_repo / "docs-registry.yaml").write_text(yaml.safe_dump(reg, sort_keys=False))
    result = run_script("doctor.py", str(tmp_repo))
    assert result.returncode == 1
    assert "past their review cadence" in result.stdout
    assert "ARCHITECTURE.md" in result.stdout


def test_doctor_gitignore_excludes_files(tmp_repo, write_md, write_doc_plan):
    """When inside a git checkout, .gitignore-excluded .md files don't count as unregistered."""
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    subprocess.run(["git", "init"], cwd=tmp_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_repo, check=True)
    # Create a stray .md file that .gitignore excludes.
    (tmp_repo / ".gitignore").write_text("ignored/\n")
    (tmp_repo / "ignored").mkdir()
    (tmp_repo / "ignored" / "PROCESS.md").write_text("# Ignored\n")
    subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True)
    subprocess.run(["git", "commit", "-m", "init", "--no-verify"], cwd=tmp_repo, check=True,
                   capture_output=True)
    result = run_script("doctor.py", str(tmp_repo))
    # The gitignored doc must NOT be flagged as unregistered.
    assert "ignored/PROCESS.md" not in result.stdout


def test_doctor_detects_unsupported_registry_version(tmp_repo, write_md, write_doc_plan):
    _setup_healthy_ecosystem(tmp_repo, write_md, write_doc_plan)
    reg = yaml.safe_load((tmp_repo / "docs-registry.yaml").read_text())
    reg["version"] = 99
    (tmp_repo / "docs-registry.yaml").write_text(yaml.safe_dump(reg, sort_keys=False))
    result = run_script("doctor.py", str(tmp_repo))
    assert result.returncode == 2  # critical
    assert "version" in result.stdout.lower() or "version" in result.stderr.lower()


def test_doctor_handles_glob_patterns(tmp_repo, write_md):
    """Various glob patterns should all be recognized correctly when paths exist."""
    write_md("README.md", "# X\n")
    write_md("src/main.py", "x")
    write_md("src/sub/deep.py", "x")
    write_md("package.json", "{}")
    write_md("vite.config.ts", "x")

    # Custom plan with various glob shapes
    plan = {
        "project_name": "x",
        "docs": [
            {
                "filename": "README.md",
                "disposition": "adopt",
                "generate": False,
                "existing_path": "README.md",
                "custom": False,
                "owns": ["overview"],
                "paths": [
                    "package.json",       # Literal file
                    "src/**",             # Recursive directory match
                    "src/main.py",        # Literal nested file
                    "*.config.ts",        # Glob in root
                ],
                "cadence": "major-changes",
            },
        ],
    }
    import json as _json
    meta = tmp_repo / ".docs-meta"
    meta.mkdir(exist_ok=True)
    (meta / "doc-plan.json").write_text(_json.dumps(plan))

    run_script("build_registry.py", str(meta / "doc-plan.json"), str(tmp_repo))
    out_dir = tmp_repo / ".github" / "workflows"
    out_dir.mkdir(parents=True)
    run_script("generate_action.py", str(tmp_repo / "docs-registry.yaml"), str(out_dir))
    run_script("append_audit.py", "--log", str(tmp_repo / "DOCS_AUDIT_LOG.md"), "--init")

    result = run_script("doctor.py", str(tmp_repo))
    # All paths exist, so registry_paths_exist should pass
    assert "Registry references" not in result.stdout
