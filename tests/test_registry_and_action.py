"""Tests for build_registry.py and generate_action.py — they work as a pair."""
import json
import yaml
from .conftest import run_script


def test_build_registry_produces_both_files(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan()
    result = run_script("build_registry.py", str(plan_path), str(tmp_repo))
    assert result.returncode == 0
    assert (tmp_repo / "docs-registry.yaml").exists()
    assert (tmp_repo / "DOCS_REGISTRY.md").exists()


def test_registry_yaml_parses(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    reg = yaml.safe_load((tmp_repo / "docs-registry.yaml").read_text())
    assert reg["version"] == 1
    assert len(reg["docs"]) == 2
    assert reg["docs"][0]["file"] == "README.md"


def test_registry_origin_mapped_from_disposition(tmp_repo, write_doc_plan):
    """disposition='adopt' should become origin='adopted' in the registry."""
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    reg = yaml.safe_load((tmp_repo / "docs-registry.yaml").read_text())
    readme = [d for d in reg["docs"] if d["file"] == "README.md"][0]
    assert readme["origin"] == "adopted"
    arch = [d for d in reg["docs"] if d["file"] == "ARCHITECTURE.md"][0]
    assert arch["origin"] == "generated"


def test_registry_md_table_renders_cleanly(tmp_repo, write_doc_plan):
    """All rows in the ownership table must be properly aligned (no leading whitespace)."""
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    md = (tmp_repo / "DOCS_REGISTRY.md").read_text()
    lines = md.split("\n")
    # Find ownership table rows
    table_rows = [l for l in lines if l.startswith("| `")]
    assert len(table_rows) >= 2
    # Each row must start with "| `" (no leading spaces)
    for row in table_rows:
        assert not row.startswith(" "), f"Row has leading whitespace: {row!r}"


def test_auto_xref_detects_overlaps(tmp_repo):
    """Two docs that share a code path should appear in the cross-reference table."""
    plan = {
        "project_name": "x",
        "docs": [
            {
                "filename": "A.md",
                "disposition": "generate",
                "generate": True,
                "owns": ["topic-x"],
                "paths": ["nx.json", "src/**"],
                "cadence": "on-change",
            },
            {
                "filename": "B.md",
                "disposition": "generate",
                "generate": True,
                "owns": ["topic-x"],  # Same topic too
                "paths": ["nx.json"],  # Shared path
                "cadence": "on-change",
            },
        ],
    }
    plan_path = tmp_repo / "plan.json"
    plan_path.write_text(json.dumps(plan))
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    md = (tmp_repo / "DOCS_REGISTRY.md").read_text()
    # Cross-reference table should include nx.json since both docs map to it
    assert "`nx.json` (code path)" in md
    assert "topic-x" in md


def test_generated_action_yaml_parses(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    out_dir = tmp_repo / ".github" / "workflows"
    out_dir.mkdir(parents=True)
    result = run_script("generate_action.py",
                        str(tmp_repo / "docs-registry.yaml"),
                        str(out_dir))
    assert result.returncode == 0
    action_path = out_dir / "docs-check.yml"
    assert action_path.exists()
    # Must parse as valid YAML
    parsed = yaml.safe_load(action_path.read_text())
    assert "jobs" in parsed
    assert "docs-check" in parsed["jobs"]


def test_generated_action_includes_path_mappings(tmp_repo, write_doc_plan):
    plan_path = write_doc_plan()
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    out_dir = tmp_repo / ".github" / "workflows"
    out_dir.mkdir(parents=True)
    run_script("generate_action.py",
               str(tmp_repo / "docs-registry.yaml"),
               str(out_dir))
    action = (out_dir / "docs-check.yml").read_text()
    # Both docs in the fixture have paths — both should appear in check calls
    assert 'check "package\\.json' in action
    assert 'check "src/.*' in action  # Glob translation: src/** → src/.*
    assert '"README.md"' in action
    assert '"ARCHITECTURE.md"' in action


def test_generated_action_glob_translation(tmp_repo):
    """src/** must translate to src/.* (not src/.[^/]*)."""
    plan = {
        "project_name": "x",
        "docs": [{
            "filename": "X.md",
            "disposition": "generate",
            "generate": True,
            "owns": [],
            "paths": ["src/**", "*.config.*"],
            "cadence": "on-change",
        }],
    }
    plan_path = tmp_repo / "plan.json"
    plan_path.write_text(json.dumps(plan))
    run_script("build_registry.py", str(plan_path), str(tmp_repo))
    out_dir = tmp_repo / ".github" / "workflows"
    out_dir.mkdir(parents=True)
    run_script("generate_action.py", str(tmp_repo / "docs-registry.yaml"), str(out_dir))
    action = (out_dir / "docs-check.yml").read_text()
    assert "src/.*" in action
    assert "src/.[^/]*" not in action  # Bug regression check
    assert "[^/]*\\.config\\.[^/]*" in action
