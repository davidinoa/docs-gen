"""Tests for validate_plan.py."""
import json
from .conftest import run_script


def test_validate_clean_plan_passes(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan()
    result = run_script("validate_plan.py", str(plan_path))
    assert result.returncode == 0


def test_validate_missing_filename(tmp_repo):
    plan = {"project_name": "x", "docs": [{"disposition": "generate"}]}
    p = tmp_repo / "plan.json"
    p.write_text(json.dumps(plan))
    result = run_script("validate_plan.py", str(p))
    assert result.returncode == 1
    assert "filename" in result.stderr


def test_validate_invalid_disposition(tmp_repo):
    plan = {
        "project_name": "x",
        "docs": [{"filename": "F.md", "disposition": "nonsense", "generate": True}],
    }
    p = tmp_repo / "plan.json"
    p.write_text(json.dumps(plan))
    result = run_script("validate_plan.py", str(p))
    assert result.returncode == 1
    assert "Invalid disposition" in result.stderr


def test_validate_inconsistent_generate_flag(tmp_repo):
    """disposition=adopt with generate=True is a contradiction."""
    plan = {
        "project_name": "x",
        "docs": [{
            "filename": "README.md",
            "disposition": "adopt",
            "generate": True,
            "existing_path": "README.md",
        }],
    }
    p = tmp_repo / "plan.json"
    p.write_text(json.dumps(plan))
    result = run_script("validate_plan.py", str(p))
    assert result.returncode == 1
    assert "expects generate=False" in result.stderr


def test_validate_duplicate_filename(tmp_repo):
    plan = {
        "project_name": "x",
        "docs": [
            {"filename": "README.md", "disposition": "adopt", "generate": False, "existing_path": "README.md"},
            {"filename": "README.md", "disposition": "augment", "generate": True, "existing_path": "README.md"},
        ],
    }
    p = tmp_repo / "plan.json"
    p.write_text(json.dumps(plan))
    result = run_script("validate_plan.py", str(p))
    assert result.returncode == 1
    assert "Duplicate filename" in result.stderr


def test_validate_paths_not_list(tmp_repo):
    plan = {
        "project_name": "x",
        "docs": [{
            "filename": "ARCHITECTURE.md",
            "disposition": "generate",
            "generate": True,
            "paths": "should-be-a-list",
        }],
    }
    p = tmp_repo / "plan.json"
    p.write_text(json.dumps(plan))
    result = run_script("validate_plan.py", str(p))
    assert result.returncode == 1
    assert "must be a list" in result.stderr


def test_validate_warns_on_custom_for_canonical_name(tmp_repo):
    """Marking a canonical filename as custom is suspicious — warn."""
    plan = {
        "project_name": "x",
        "docs": [{
            "filename": "README.md",
            "disposition": "enroll",
            "generate": False,
            "custom": True,
            "existing_path": "README.md",
        }],
    }
    p = tmp_repo / "plan.json"
    p.write_text(json.dumps(plan))
    result = run_script("validate_plan.py", str(p))
    assert result.returncode == 2  # warnings, no errors
    assert "marked custom=true" in result.stderr


def test_validate_warns_on_non_custom_for_unknown_name(tmp_repo):
    """A non-standard filename should be marked custom — warn otherwise."""
    plan = {
        "project_name": "x",
        "docs": [{
            "filename": "WEIRD.md",
            "disposition": "generate",
            "generate": True,
            "custom": False,
        }],
    }
    p = tmp_repo / "plan.json"
    p.write_text(json.dumps(plan))
    result = run_script("validate_plan.py", str(p))
    assert result.returncode == 2
    assert "custom=true" in result.stderr
