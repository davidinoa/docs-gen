"""Tests for v0.3.0 features: summaries, owners, codeowners, snapshot,
lookup, sync, init, and the --strict generate-action mode."""

import json
from datetime import date
from pathlib import Path

import yaml
from .conftest import cli, run_script


# ── Registry summaries ──────────────────────────────────────────────────────

def test_summary_extracted_from_existing_doc(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# Project\n\nThis is the project's elevator pitch. It does X.\n")
    write_md("ARCHITECTURE.md", "# Arch\n\nHigh level design notes go here.\n")
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    reg = yaml.safe_load((tmp_repo / "docs-registry.yaml").read_text())
    by_file = {d["file"]: d for d in reg["docs"]}
    assert "elevator pitch" in by_file["README.md"]["summary"]
    assert "High level design" in by_file["ARCHITECTURE.md"]["summary"]


def test_summary_uses_plan_override(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan({
        "docs": [{
            "filename": "README.md",
            "disposition": "generate",
            "generate": True,
            "summary": "explicit summary from the plan",
            "owns": [], "paths": [], "cadence": "on-change",
        }],
    })
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    reg = yaml.safe_load((tmp_repo / "docs-registry.yaml").read_text())
    assert reg["docs"][0]["summary"] == "explicit summary from the plan"


def test_registry_md_renders_summaries(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# Project\n\nKey description.\n")
    write_md("ARCHITECTURE.md", "# Arch\n\nDesign overview.\n")
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    md = (tmp_repo / "DOCS_REGISTRY.md").read_text()
    assert "## Doc Summaries" in md
    assert "Key description" in md or "Design overview" in md


# ── Owners + CODEOWNERS ─────────────────────────────────────────────────────

def test_owners_propagate_to_registry(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan({
        "docs": [{
            "filename": "ARCHITECTURE.md",
            "disposition": "generate", "generate": True,
            "owns": [], "paths": [], "cadence": "on-change",
            "owners": ["@alice", "@team-arch"],
        }],
    })
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    reg = yaml.safe_load((tmp_repo / "docs-registry.yaml").read_text())
    assert reg["docs"][0]["owners"] == ["@alice", "@team-arch"]


def test_codeowners_export_writes_file(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan({
        "docs": [
            {"filename": "ARCHITECTURE.md", "disposition": "generate", "generate": True,
             "owns": [], "paths": [], "cadence": "on-change",
             "owners": ["@alice", "@team-arch"]},
            {"filename": "RUNBOOK.md", "disposition": "generate", "generate": True,
             "owns": [], "paths": [], "cadence": "on-change",
             "owners": ["@bob"]},
        ],
    })
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    out = tmp_repo / ".github" / "CODEOWNERS"
    result = cli("codeowners", str(tmp_repo / "docs-registry.yaml"), str(out))
    assert result.returncode == 0
    content = out.read_text()
    assert "ARCHITECTURE.md @alice @team-arch" in content
    assert "RUNBOOK.md @bob" in content


def test_codeowners_stdout(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan({
        "docs": [{"filename": "ARCHITECTURE.md", "disposition": "generate", "generate": True,
                  "owns": [], "paths": [], "cadence": "on-change", "owners": ["@alice"]}],
    })
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    result = cli("codeowners", str(tmp_repo / "docs-registry.yaml"), "--stdout")
    assert result.returncode == 0
    assert "ARCHITECTURE.md @alice" in result.stdout


def test_codeowners_skips_docs_without_owners(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan()  # default fixture has no owners
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    result = cli("codeowners", str(tmp_repo / "docs-registry.yaml"), "--stdout")
    assert "No docs declare" in result.stdout


# ── --strict generate-action ────────────────────────────────────────────────

def test_generate_action_strict_emits_fail_step(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    out_dir = tmp_repo / ".github" / "workflows"
    out_dir.mkdir(parents=True)
    result = cli("generate-action", str(tmp_repo / "docs-registry.yaml"),
                 str(out_dir), "--strict")
    assert result.returncode == 0
    action = (out_dir / "docs-check.yml").read_text()
    assert "Fail when docs aren't updated" in action
    assert "exit 1" in action


def test_generate_action_default_is_soft(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    out_dir = tmp_repo / ".github" / "workflows"
    out_dir.mkdir(parents=True)
    cli("generate-action", str(tmp_repo / "docs-registry.yaml"), str(out_dir))
    action = (out_dir / "docs-check.yml").read_text()
    assert "Fail when docs aren't updated" not in action
    assert "never blocks merging" in action


# ── snapshot ────────────────────────────────────────────────────────────────

def test_snapshot_creates_frozen_copy(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# X\n\nProject.\n")
    write_md("ARCHITECTURE.md", "# Arch\n\nDesign.\n")
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    result = cli("snapshot", "v1.0.0", "--repo", str(tmp_repo))
    assert result.returncode == 0
    snap = tmp_repo / ".docs-meta" / "snapshots" / "v1.0.0"
    assert (snap / "docs-registry.yaml").exists()
    assert (snap / "README.md").exists()
    assert (snap / "ARCHITECTURE.md").exists()
    manifest = json.loads((snap / "manifest.json").read_text())
    assert manifest["name"] == "v1.0.0"
    assert "README.md" in manifest["files"]


def test_snapshot_records_git_ref(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# X\n")
    plan_path = write_doc_plan({"docs": [
        {"filename": "README.md", "disposition": "adopt", "generate": False,
         "existing_path": "README.md", "owns": [], "paths": [], "cadence": "major-changes"},
    ]})
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    cli("snapshot", "release-1", "--repo", str(tmp_repo), "--git-ref", "v1.2.3")
    manifest = json.loads(
        (tmp_repo / ".docs-meta" / "snapshots" / "release-1" / "manifest.json").read_text()
    )
    assert manifest["git_ref"] == "v1.2.3"


def test_snapshot_list_shows_existing(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# X\n")
    plan_path = write_doc_plan({"docs": [
        {"filename": "README.md", "disposition": "adopt", "generate": False,
         "existing_path": "README.md", "owns": [], "paths": [], "cadence": "major-changes"},
    ]})
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    cli("snapshot", "snap1", "--repo", str(tmp_repo))
    cli("snapshot", "snap2", "--repo", str(tmp_repo))
    result = cli("snapshot", "--repo", str(tmp_repo), "--list")
    assert result.returncode == 0
    assert "snap1" in result.stdout
    assert "snap2" in result.stdout


def test_snapshot_dry_run_does_not_write(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# X\n")
    plan_path = write_doc_plan({"docs": [
        {"filename": "README.md", "disposition": "adopt", "generate": False,
         "existing_path": "README.md", "owns": [], "paths": [], "cadence": "major-changes"},
    ]})
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    result = cli("snapshot", "preview", "--repo", str(tmp_repo), "--dry-run")
    assert result.returncode == 0
    assert not (tmp_repo / ".docs-meta" / "snapshots" / "preview").exists()


# ── lookup ──────────────────────────────────────────────────────────────────

def _build_registry_for_lookup(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# Project\n\nThe rate-limited API gateway.\n")
    write_md("ARCHITECTURE.md", "# Arch\n\nWe use Postgres for storage.\n")
    plan = {
        "project_name": "x",
        "docs": [
            {"filename": "README.md", "disposition": "adopt", "generate": False,
             "existing_path": "README.md", "owns": ["overview"], "paths": ["package.json"],
             "cadence": "major-changes"},
            {"filename": "ARCHITECTURE.md", "disposition": "generate", "generate": True,
             "owns": ["system design", "auth"], "paths": ["src/**"], "cadence": "on-change"},
        ],
    }
    plan_path = tmp_repo / "plan.json"
    plan_path.write_text(json.dumps(plan))
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    return tmp_repo / "docs-registry.yaml"


def test_lookup_by_path_glob_match(tmp_repo, write_md, write_doc_plan):
    reg = _build_registry_for_lookup(tmp_repo, write_md, write_doc_plan)
    result = cli("lookup", "--registry", str(reg), "--path", "src/auth/login.ts")
    assert result.returncode == 0
    assert "ARCHITECTURE.md" in result.stdout
    assert "README.md" not in result.stdout


def test_lookup_by_owns_substring(tmp_repo, write_md, write_doc_plan):
    reg = _build_registry_for_lookup(tmp_repo, write_md, write_doc_plan)
    result = cli("lookup", "--registry", str(reg), "--owns", "AUTH")
    assert result.returncode == 0
    assert "ARCHITECTURE.md" in result.stdout


def test_lookup_by_query_summary(tmp_repo, write_md, write_doc_plan):
    reg = _build_registry_for_lookup(tmp_repo, write_md, write_doc_plan)
    result = cli("lookup", "--registry", str(reg), "--query", "Postgres")
    assert result.returncode == 0
    assert "ARCHITECTURE.md" in result.stdout


def test_lookup_no_matches_returns_2(tmp_repo, write_md, write_doc_plan):
    reg = _build_registry_for_lookup(tmp_repo, write_md, write_doc_plan)
    result = cli("lookup", "--registry", str(reg), "--path", "rust-only/foo.rs")
    assert result.returncode == 2


def test_lookup_json_output(tmp_repo, write_md, write_doc_plan):
    reg = _build_registry_for_lookup(tmp_repo, write_md, write_doc_plan)
    result = cli("lookup", "--registry", str(reg), "--owns", "auth", "--json")
    data = json.loads(result.stdout)
    assert any(d["file"] == "ARCHITECTURE.md" for d in data)
    assert all("why" in d for d in data)


def test_lookup_requires_a_filter(tmp_repo, write_md, write_doc_plan):
    reg = _build_registry_for_lookup(tmp_repo, write_md, write_doc_plan)
    result = cli("lookup", "--registry", str(reg))
    assert result.returncode == 1


# ── sync ────────────────────────────────────────────────────────────────────

def test_sync_produces_registry_action_and_audit_log(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# X\n\nDesc\n")
    write_md("ARCHITECTURE.md", "# Arch\n\nDesc\n")
    plan_path = write_doc_plan()
    result = cli("sync", str(plan_path), "--output-dir", str(tmp_repo),
                 "--workflows-dir", str(tmp_repo / ".github" / "workflows"),
                 "--audit-log", str(tmp_repo / "DOCS_AUDIT_LOG.md"))
    assert result.returncode == 0
    assert (tmp_repo / "docs-registry.yaml").exists()
    assert (tmp_repo / "DOCS_REGISTRY.md").exists()
    assert (tmp_repo / ".github" / "workflows" / "docs-check.yml").exists()
    assert (tmp_repo / "DOCS_AUDIT_LOG.md").exists()


def test_sync_skip_audit(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# X\n")
    plan_path = write_doc_plan()
    result = cli("sync", str(plan_path), "--output-dir", str(tmp_repo),
                 "--workflows-dir", str(tmp_repo / ".github" / "workflows"),
                 "--skip-audit")
    assert result.returncode == 0
    assert not (tmp_repo / "DOCS_AUDIT_LOG.md").exists()


def test_sync_strict_flag_passes_through(tmp_repo, write_md, write_doc_plan):
    write_md("README.md", "# X\n")
    plan_path = write_doc_plan()
    cli("sync", str(plan_path), "--output-dir", str(tmp_repo),
        "--workflows-dir", str(tmp_repo / ".github" / "workflows"),
        "--audit-log", str(tmp_repo / "DOCS_AUDIT_LOG.md"),
        "--strict")
    action = (tmp_repo / ".github" / "workflows" / "docs-check.yml").read_text()
    assert "Fail when docs aren't updated" in action


# ── init ────────────────────────────────────────────────────────────────────

def test_init_writes_minimal_plan(tmp_repo):
    (tmp_repo / "package.json").write_text('{"name": "my-app"}')
    result = cli("init", "--repo", str(tmp_repo), "--skip-sync")
    assert result.returncode == 0
    plan_path = tmp_repo / ".docs-meta" / "doc-plan.json"
    assert plan_path.exists()
    plan = json.loads(plan_path.read_text())
    assert plan["project_name"] == "my-app"
    filenames = {d["filename"] for d in plan["docs"]}
    assert {"README.md", "ARCHITECTURE.md", "GOTCHAS.md"}.issubset(filenames)


def test_init_full_preset_includes_more_docs(tmp_repo):
    result = cli("init", "--repo", str(tmp_repo), "--preset", "full", "--skip-sync")
    assert result.returncode == 0
    plan = json.loads((tmp_repo / ".docs-meta" / "doc-plan.json").read_text())
    filenames = {d["filename"] for d in plan["docs"]}
    # The full taxonomy should include items the minimal preset omits.
    assert "ENVIRONMENT.md" in filenames
    assert "CHANGELOG.md" in filenames


def test_init_refuses_overwrite_without_force(tmp_repo):
    cli("init", "--repo", str(tmp_repo), "--skip-sync")
    result = cli("init", "--repo", str(tmp_repo), "--skip-sync")
    assert result.returncode == 1


def test_init_force_overwrites(tmp_repo):
    cli("init", "--repo", str(tmp_repo), "--skip-sync")
    result = cli("init", "--repo", str(tmp_repo), "--skip-sync", "--force",
                 "--name", "renamed-project")
    assert result.returncode == 0
    plan = json.loads((tmp_repo / ".docs-meta" / "doc-plan.json").read_text())
    assert plan["project_name"] == "renamed-project"


def test_init_scaffold_writes_stub_files(tmp_repo):
    result = cli("init", "--repo", str(tmp_repo), "--skip-sync", "--scaffold")
    assert result.returncode == 0
    assert (tmp_repo / "README.md").exists()
    assert (tmp_repo / "ARCHITECTURE.md").exists()
    body = (tmp_repo / "ARCHITECTURE.md").read_text()
    assert body.startswith("# Architecture")


def test_init_with_sync_produces_full_ecosystem(tmp_repo):
    """Default flow: init scaffolds the plan AND runs sync."""
    (tmp_repo / "package.json").write_text('{"name": "demo"}')
    result = cli("init", "--repo", str(tmp_repo), "--scaffold")
    assert result.returncode == 0
    assert (tmp_repo / "docs-registry.yaml").exists()
    assert (tmp_repo / "DOCS_REGISTRY.md").exists()
    assert (tmp_repo / ".github" / "workflows" / "docs-check.yml").exists()
    assert (tmp_repo / "DOCS_AUDIT_LOG.md").exists()
