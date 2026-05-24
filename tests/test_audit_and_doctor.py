"""Tests for append_audit.py and doctor.py."""
import json
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
