"""Tests for state.py."""
import json
from .conftest import run_script


def test_init_creates_state_file(tmp_repo):
    result = run_script("state.py", "init", str(tmp_repo))
    assert result.returncode == 0
    state_file = tmp_repo / ".docs-meta" / "state.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["current_step"] == "specs"
    assert state["completed_steps"] == []


def test_init_refuses_overwrite(tmp_repo):
    run_script("state.py", "init", str(tmp_repo))
    result = run_script("state.py", "init", str(tmp_repo))
    assert result.returncode == 1
    assert "already exists" in result.stderr


def test_advance_in_order(tmp_repo):
    run_script("state.py", "init", str(tmp_repo))
    result = run_script("state.py", "advance", "--repo", str(tmp_repo), "--step", "specs")
    assert result.returncode == 0
    state = json.loads((tmp_repo / ".docs-meta" / "state.json").read_text())
    assert "specs" in state["completed_steps"]
    assert state["current_step"] == "interview"


def test_advance_rejects_skip_ahead(tmp_repo):
    """Skipping ahead without --force should fail."""
    run_script("state.py", "init", str(tmp_repo))
    result = run_script("state.py", "advance", "--repo", str(tmp_repo), "--step", "validate")
    assert result.returncode == 2
    assert "Skipping ahead" in result.stderr


def test_advance_force_allows_skip(tmp_repo):
    run_script("state.py", "init", str(tmp_repo))
    result = run_script("state.py", "advance", "--repo", str(tmp_repo),
                        "--step", "validate", "--force")
    assert result.returncode == 0
    state = json.loads((tmp_repo / ".docs-meta" / "state.json").read_text())
    assert "validate" in state["completed_steps"]


def test_advance_records_artifacts_and_outputs(tmp_repo):
    run_script("state.py", "init", str(tmp_repo))
    run_script("state.py", "advance", "--repo", str(tmp_repo), "--step", "specs",
               "--artifact", "assessment=.docs-meta/assess.json",
               "--output", "SPECS.md")
    state = json.loads((tmp_repo / ".docs-meta" / "state.json").read_text())
    assert state["artifacts"]["assessment"] == ".docs-meta/assess.json"
    assert "SPECS.md" in state["outputs_written"]


def test_status_without_state_fails(tmp_repo):
    result = run_script("state.py", "status", "--repo", str(tmp_repo))
    assert result.returncode == 1


def test_get_field(tmp_repo):
    run_script("state.py", "init", str(tmp_repo))
    result = run_script("state.py", "get", "--repo", str(tmp_repo), "--field", "current_step")
    assert result.returncode == 0
    assert result.stdout.strip() == "specs"


def test_reset_requires_yes(tmp_repo):
    run_script("state.py", "init", str(tmp_repo))
    result = run_script("state.py", "reset", "--repo", str(tmp_repo))
    assert result.returncode == 1
    state_file = tmp_repo / ".docs-meta" / "state.json"
    assert state_file.exists()  # Not deleted

    result = run_script("state.py", "reset", "--repo", str(tmp_repo), "--yes")
    assert result.returncode == 0
    assert not state_file.exists()


def test_init_dry_run_does_not_write(tmp_repo):
    result = run_script("state.py", "init", str(tmp_repo), "--dry-run")
    assert result.returncode == 0
    assert not (tmp_repo / ".docs-meta" / "state.json").exists()


def test_revert_rewinds_pointer(tmp_repo):
    run_script("state.py", "init", str(tmp_repo))
    # Advance through several steps
    for step in ["specs", "interview", "scan", "plan"]:
        run_script("state.py", "advance", "--repo", str(tmp_repo), "--step", step)
    pre = json.loads((tmp_repo / ".docs-meta" / "state.json").read_text())
    assert pre["current_step"] == "generate"
    assert "plan" in pre["completed_steps"]

    result = run_script("state.py", "revert", "--repo", str(tmp_repo), "--step", "scan")
    assert result.returncode == 0
    state = json.loads((tmp_repo / ".docs-meta" / "state.json").read_text())
    assert state["current_step"] == "scan"
    # scan and everything after it must be gone from completed
    assert "scan" not in state["completed_steps"]
    assert "plan" not in state["completed_steps"]
    # Earlier steps are preserved
    assert "specs" in state["completed_steps"]
    assert "interview" in state["completed_steps"]
