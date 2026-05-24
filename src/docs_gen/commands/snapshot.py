"""snapshot — freeze the current docs ecosystem under .docs-meta/snapshots/<name>/.

Future-you wants to see what `ARCHITECTURE.md` looked like at v1.0 even
if it has since drifted. Git history serves the same purpose, but a
snapshot bundle keeps the registry + every referenced doc together as
a single dated artifact you can diff or hand off without spelunking.

Layout:
    .docs-meta/snapshots/<name>/
        manifest.json       — name, created_at, files list, optional git ref
        docs-registry.yaml  — copy of the registry at snapshot time
        <doc>.md            — copy of each registry-referenced file

Usage:
    docs-gen snapshot <name>
    docs-gen snapshot v1.0 --registry docs-registry.yaml --repo .
    docs-gen snapshot release-2026Q2 --git-ref v2.0.1
    docs-gen snapshot --list
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    import sys
    print("❌ pyyaml required. Install: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(1)

from docs_gen import SUPPORTED_REGISTRY_VERSIONS, VersionMismatch, check_version, log


def _snapshots_dir(repo: Path) -> Path:
    return repo / ".docs-meta" / "snapshots"


def list_snapshots(repo: Path) -> list[dict]:
    d = _snapshots_dir(repo)
    if not d.exists():
        return []
    out = []
    for sub in sorted(d.iterdir()):
        if not sub.is_dir():
            continue
        manifest_path = sub / "manifest.json"
        manifest = {}
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text())
            except json.JSONDecodeError:
                manifest = {"error": "manifest unreadable"}
        manifest["name"] = sub.name
        manifest["path"] = str(sub.relative_to(repo))
        out.append(manifest)
    return out


def create_snapshot(
    name: str,
    repo: Path,
    registry_path: Path,
    *,
    git_ref: str | None = None,
    dry_run: bool = False,
) -> Path:
    """Copy the registry and every referenced doc into a dated snapshot dir.

    Returns the snapshot directory path (whether the write happened or was
    skipped under --dry-run).
    """
    snapshot_root = _snapshots_dir(repo) / name

    with open(registry_path) as f:
        registry = yaml.safe_load(f)
    check_version(registry.get("version"), SUPPORTED_REGISTRY_VERSIONS, what=str(registry_path))

    docs = registry.get("docs", [])
    files_to_copy: list[tuple[Path, str]] = []
    missing: list[str] = []
    for d in docs:
        filename = d.get("file")
        if not filename:
            continue
        src = repo / filename
        if src.is_file():
            files_to_copy.append((src, filename))
        else:
            # Try to find it elsewhere in the repo (some teams nest under docs/).
            matches = [p for p in repo.rglob(filename)
                       if "node_modules" not in p.parts and ".git" not in p.parts]
            if matches:
                files_to_copy.append((matches[0], filename))
            else:
                missing.append(filename)

    manifest = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_ref": git_ref,
        "registry_source": str(registry_path),
        "files": [name for _, name in files_to_copy],
        "missing": missing,
    }

    if dry_run:
        log.info(f"[dry-run] would create snapshot at: {snapshot_root}")
        log.info(f"[dry-run] would copy registry: {registry_path.name}")
        for _, rel in files_to_copy:
            log.info(f"[dry-run] would copy doc: {rel}")
        if missing:
            log.warn(f"[dry-run] {len(missing)} registered doc(s) not found in repo: {', '.join(missing)}")
        return snapshot_root

    snapshot_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(registry_path, snapshot_root / "docs-registry.yaml")
    for src, rel in files_to_copy:
        dest = snapshot_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    (snapshot_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    log.ok(f"Snapshot written: {snapshot_root}")
    log.info(f"  {len(files_to_copy)} doc(s) frozen")
    if missing:
        log.warn(f"  {len(missing)} registered doc(s) missing from repo: {', '.join(missing)}")
    return snapshot_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs-gen snapshot",
        description="Freeze the docs registry + referenced files under .docs-meta/snapshots/<name>/.",
    )
    parser.add_argument("name", nargs="?",
                        help="Snapshot name (e.g., v1.0, q2-2026). Omit with --list.")
    parser.add_argument("--repo", default=".",
                        help="Repository root (default: current directory)")
    parser.add_argument("--registry", default="docs-registry.yaml",
                        help="Path to docs-registry.yaml (default: docs-registry.yaml)")
    parser.add_argument("--git-ref", default=None,
                        help="Record this git ref/tag in the snapshot manifest (informational)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be copied without modifying the filesystem")
    parser.add_argument("--list", action="store_true",
                        help="List existing snapshots and exit")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()

    if args.list:
        items = list_snapshots(repo)
        if not items:
            log.info(f"No snapshots yet under {_snapshots_dir(repo)}")
            return 0
        for m in items:
            created = m.get("created_at", "?")
            count = len(m.get("files", []))
            ref = m.get("git_ref")
            ref_part = f" (git: {ref})" if ref else ""
            print(f"{m['name']}\t{created}\t{count} files{ref_part}")
        return 0

    if not args.name:
        parser.error("snapshot name is required (or pass --list)")

    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = repo / registry_path
    if not registry_path.is_file():
        log.error(f"Registry not found: {registry_path}")
        return 1

    try:
        create_snapshot(
            args.name, repo, registry_path,
            git_ref=args.git_ref, dry_run=args.dry_run,
        )
    except VersionMismatch as exc:
        log.error(str(exc))
        return 1
    except yaml.YAMLError as exc:
        log.error(f"Could not parse {registry_path}: {exc}")
        return 1
    return 0
