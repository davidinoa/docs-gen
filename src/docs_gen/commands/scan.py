"""Discover existing documentation in a repository.

Reads doc type definitions from the packaged doc-types.yaml. To add a new
doc type, edit the YAML — not this module.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from docs_gen import config_path, log


def load_doc_types(yaml_path: Path) -> dict:
    """Load doc type config. Returns dict with doc_types, skip_files, search_dirs."""
    with open(yaml_path) as f:
        config = yaml.safe_load(f)
    return {
        "doc_types": {dt["name"]: dt for dt in config["doc_types"]},
        "skip_files": set(config.get("skip_files", [])),
        "search_dirs": config.get("search_dirs", [".", "docs"]),
    }


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def scan_repo(repo_path: str | Path, doc_types_config: dict) -> dict:
    """Scan a repo for known docs and uncategorized .md files.

    Returns a structured dict with:
      - standard_docs: dict of doc type → metadata
      - other_docs: list of unclaimed .md files
      - health_system: presence of registry/audit/action/state files
    """
    repo = Path(repo_path).resolve()
    doc_types = doc_types_config["doc_types"]
    skip_files = doc_types_config["skip_files"]
    search_dirs = doc_types_config["search_dirs"]

    result = {
        "repo_path": str(repo),
        "standard_docs": {},
        "other_docs": [],
        "health_system": {
            "registry_exists": False,
            "registry_path": None,
            "audit_log_exists": False,
            "docs_check_action_exists": False,
            "state_file_exists": False,
        },
    }

    for registry_candidate in ["DOCS_REGISTRY.md", "docs-registry.yaml", "docs/DOCS_REGISTRY.md"]:
        if (repo / registry_candidate).exists():
            result["health_system"]["registry_exists"] = True
            result["health_system"]["registry_path"] = registry_candidate
            break

    result["health_system"]["audit_log_exists"] = (repo / "DOCS_AUDIT_LOG.md").exists()
    result["health_system"]["docs_check_action_exists"] = (
        repo / ".github" / "workflows" / "docs-check.yml"
    ).exists()
    result["health_system"]["state_file_exists"] = (repo / ".docs-meta" / "state.json").exists()

    claimed_paths: set[str] = set()
    for doc_type_name, doc_type in doc_types.items():
        for candidate in doc_type.get("scan_patterns", []):
            path = repo / candidate
            if path.exists():
                rel = str(path.relative_to(repo))
                is_dir = path.is_dir()
                content = "" if is_dir else _read_safe(path)
                canonical = doc_type["canonical_filename"]
                result["standard_docs"][doc_type_name] = {
                    "found_at": rel,
                    "canonical_name": canonical,
                    "is_canonical_name": path.name == canonical,
                    "is_directory": is_dir,
                    "size_bytes": path.stat().st_size if path.is_file() else 0,
                    "line_count": len(content.splitlines()),
                    "preview": content[:600] if content else "(directory)",
                    "category": doc_type.get("category", ""),
                }
                claimed_paths.add(rel)
                break

    for search_dir in search_dirs:
        d = repo / search_dir
        if not d.exists() or not d.is_dir():
            continue
        for md_file in sorted(d.glob("*.md")):
            rel = str(md_file.relative_to(repo))
            if rel in claimed_paths or md_file.name in skip_files:
                continue
            content = _read_safe(md_file)
            result["other_docs"].append({
                "path": rel,
                "size_bytes": md_file.stat().st_size,
                "line_count": len(content.splitlines()),
                "preview": content[:600],
            })
            claimed_paths.add(rel)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docs-gen scan", description="Discover existing documentation in a repository")
    parser.add_argument("repo_path", nargs="?", default=".", help="Path to the repo")
    parser.add_argument(
        "--doc-types",
        default=None,
        help="Override path to doc-types.yaml (default: packaged config)",
    )
    args = parser.parse_args(argv)

    yaml_path = Path(args.doc_types) if args.doc_types else config_path("doc-types.yaml")
    if not yaml_path.exists():
        log.error(f"doc-types.yaml not found at {yaml_path}")
        return 1

    log.info(f"Loading doc types from {yaml_path}")
    try:
        doc_types_config = load_doc_types(yaml_path)
    except yaml.YAMLError as exc:
        log.error(f"Failed to parse {yaml_path}: {exc}")
        return 1
    log.info(f"Scanning {args.repo_path}")

    output = scan_repo(args.repo_path, doc_types_config)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
