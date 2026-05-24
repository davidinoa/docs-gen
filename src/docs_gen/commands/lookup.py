"""lookup — find docs in the registry by code path, topic, or text query.

The registry is the index; this command is the search interface.
Designed for agents pulling docs into context before editing code, and
for humans asking "which doc do I update when I touch X?".

Usage:
    docs-gen lookup --path src/auth/login.ts
    docs-gen lookup --owns "auth"
    docs-gen lookup --query "rate limit"
    docs-gen lookup --path src/api --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required. Install: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(1)

from docs_gen import SUPPORTED_REGISTRY_VERSIONS, VersionMismatch, check_version, log


def _glob_to_regex(glob: str) -> str:
    """Translate a path glob ('src/**', 'api/*.ts') into a full-match regex."""
    DOUBLESTAR = "\x00DOUBLESTAR\x00"
    STAR = "\x00STAR\x00"
    s = glob.replace("**", DOUBLESTAR).replace("*", STAR)
    s = re.escape(s).replace(re.escape(DOUBLESTAR), ".*").replace(re.escape(STAR), "[^/]*")
    return f"^{s}$"


def _path_matches(doc_paths: list[str], query_path: str) -> list[str]:
    """Return the doc's paths that match the queried code path."""
    matches: list[str] = []
    for p in doc_paths or []:
        try:
            if re.match(_glob_to_regex(p), query_path):
                matches.append(p)
        except re.error:
            continue
    return matches


def lookup(registry: dict, *, path: str | None = None, owns: str | None = None,
           query: str | None = None) -> list[dict]:
    """Search the registry. Returns a list of {file, why, doc} match dicts."""
    results: list[dict] = []
    for doc in registry.get("docs", []):
        reasons: list[str] = []
        if path is not None:
            for matched_glob in _path_matches(doc.get("paths", []), path):
                reasons.append(f"paths matches `{matched_glob}`")
        if owns is not None:
            needle = owns.lower().strip()
            for topic in doc.get("owns", []) or []:
                if needle and needle in str(topic).lower():
                    reasons.append(f"owns: {topic}")
        if query is not None:
            haystacks = [
                str(doc.get("summary") or ""),
                doc.get("file") or "",
                " ".join(doc.get("owns") or []),
            ]
            needle = query.lower()
            for hay in haystacks:
                if needle and needle in hay.lower():
                    reasons.append("query match")
                    break
        if reasons:
            results.append({
                "file": doc["file"],
                "why": "; ".join(reasons),
                "summary": doc.get("summary") or "",
                "owns": doc.get("owns") or [],
                "paths": doc.get("paths") or [],
                "owners": doc.get("owners") or [],
                "cadence": doc.get("cadence"),
                "origin": doc.get("origin"),
            })
    return results


def _render_text(results: list[dict]) -> str:
    if not results:
        return "(no matching docs)\n"
    lines: list[str] = []
    for r in results:
        lines.append(f"{r['file']}")
        if r.get("summary"):
            lines.append(f"  {r['summary']}")
        lines.append(f"  why: {r['why']}")
        if r.get("owners"):
            lines.append(f"  owners: {', '.join(r['owners'])}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs-gen lookup",
        description="Find docs in the registry by code path, topic, or query string.",
    )
    parser.add_argument("--registry", default="docs-registry.yaml",
                        help="Path to docs-registry.yaml (default: docs-registry.yaml)")
    parser.add_argument("--path", default=None,
                        help="Find docs whose `paths` glob matches this code path")
    parser.add_argument("--owns", default=None,
                        help="Find docs whose `owns` topics contain this substring (case-insensitive)")
    parser.add_argument("--query", default=None,
                        help="Substring-search summaries, filenames, and owns topics")
    parser.add_argument("--json", action="store_true",
                        help="Emit results as JSON instead of human-readable text")
    args = parser.parse_args(argv)

    if not any([args.path, args.owns, args.query]):
        log.error("Pass at least one of --path, --owns, or --query.")
        return 1

    registry_path = Path(args.registry)
    if not registry_path.is_file():
        log.error(f"Registry not found: {registry_path}")
        return 1

    try:
        with open(registry_path) as f:
            registry = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        log.error(f"Could not parse {registry_path}: {exc}")
        return 1

    try:
        check_version(registry.get("version"), SUPPORTED_REGISTRY_VERSIONS, what=str(registry_path))
    except VersionMismatch as exc:
        log.error(str(exc))
        return 1

    results = lookup(registry, path=args.path, owns=args.owns, query=args.query)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        sys.stdout.write(_render_text(results))

    return 0 if results else 2
