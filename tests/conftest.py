"""
Shared pytest fixtures and helpers for the docs-gen test suite.

Tests invoke the docs-gen CLI via subprocess to verify end-to-end behavior
including arg parsing, exit codes, and stdout/stderr conventions.
"""
import json
import subprocess
from pathlib import Path

import pytest


def cli(*args, cwd=None) -> subprocess.CompletedProcess:
    """Invoke `docs-gen` with given args. Returns CompletedProcess; doesn't raise."""
    return subprocess.run(
        ["docs-gen", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


# Maps old script names to new subcommands so the existing test suite works unchanged.
_SCRIPT_TO_SUBCOMMAND = {
    "scan_docs.py":       "scan",
    "assess_specs.py":    "assess",
    "validate_plan.py":   "validate-plan",
    "validate_docs.py":   "validate",
    "build_registry.py":  "build-registry",
    "generate_action.py": "generate-action",
    "append_audit.py":    "audit",
    "doctor.py":          "doctor",
    "state.py":           "state",
    "docs_gen.py":        None,
}


def run_script(name: str, *args, cwd=None) -> subprocess.CompletedProcess:
    """Map old script names to docs-gen subcommands."""
    if name not in _SCRIPT_TO_SUBCOMMAND:
        raise ValueError(f"Unknown script: {name}")
    sub = _SCRIPT_TO_SUBCOMMAND[name]
    if sub is None:
        return cli(*args, cwd=cwd)
    return cli(sub, *args, cwd=cwd)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def minimal_doc_plan() -> dict:
    return {
        "project_name": "test-project",
        "generated_at": "2026-01-01",
        "docs": [
            {
                "filename": "README.md",
                "disposition": "adopt",
                "generate": False,
                "existing_path": "README.md",
                "custom": False,
                "owns": ["overview"],
                "paths": ["package.json"],
                "cadence": "major-changes",
            },
            {
                "filename": "ARCHITECTURE.md",
                "disposition": "generate",
                "generate": True,
                "custom": False,
                "owns": ["system design"],
                "paths": ["src/**"],
                "cadence": "on-change",
            },
        ],
    }


@pytest.fixture
def write_doc_plan(tmp_repo, minimal_doc_plan):
    def _write(overrides=None):
        plan = dict(minimal_doc_plan)
        if overrides:
            plan.update(overrides)
        meta_dir = tmp_repo / ".docs-meta"
        meta_dir.mkdir(exist_ok=True)
        plan_path = meta_dir / "doc-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2))
        return plan_path
    return _write


@pytest.fixture
def write_md(tmp_repo):
    def _write(name: str, content: str):
        path = tmp_repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path
    return _write
