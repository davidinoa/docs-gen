"""codeowners — export .github/CODEOWNERS from docs-registry.yaml.

Each registry entry with non-empty `owners:` becomes one line in CODEOWNERS:
the doc file path is the pattern; the owners list (GitHub usernames or
@team handles) is appended. Docs without owners are skipped.

Pair with `--strict` on `generate-action` to enforce reviewer routing on
PRs that touch doc files.

Usage:
    docs-gen codeowners <registry.yaml> [<output_path>]
    docs-gen codeowners docs-registry.yaml .github/CODEOWNERS
    docs-gen codeowners docs-registry.yaml --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required. Install: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(1)

from docs_gen import SUPPORTED_REGISTRY_VERSIONS, VersionMismatch, check_version, log


HEADER = (
    "# CODEOWNERS\n"
    "# Generated from docs-registry.yaml by `docs-gen codeowners`.\n"
    "# Do not edit directly — re-run the command instead.\n"
    "# Reference: https://docs.github.com/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners\n"
    "\n"
)


def render_codeowners(registry: dict) -> str:
    """Render CODEOWNERS content from a registry dict.

    Emits one line per doc that declares owners. The pattern is the doc's
    file path (so reviewers are routed when the doc itself is edited);
    code-path → doc-owner routing is handled by the docs-check.yml
    workflow rather than by CODEOWNERS.
    """
    lines: list[str] = []
    for doc in registry.get("docs", []):
        owners = doc.get("owners") or []
        if not owners:
            continue
        owner_cell = " ".join(owners)
        lines.append(f"{doc['file']} {owner_cell}")
    if not lines:
        lines.append("# (No docs declare `owners:` in docs-registry.yaml — nothing to route.)")
    return HEADER + "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs-gen codeowners",
        description="Export .github/CODEOWNERS from docs-registry.yaml.",
    )
    parser.add_argument("registry_yaml", help="Path to docs-registry.yaml")
    parser.add_argument("output_path", nargs="?", default=".github/CODEOWNERS",
                        help="Where to write the CODEOWNERS file (default: .github/CODEOWNERS)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print intended write without modifying the filesystem")
    parser.add_argument("--stdout", action="store_true",
                        help="Print CODEOWNERS content to stdout instead of writing a file")
    args = parser.parse_args(argv)

    try:
        with open(args.registry_yaml) as f:
            registry = yaml.safe_load(f)
    except FileNotFoundError:
        log.error(f"Registry not found: {args.registry_yaml}")
        return 1
    except yaml.YAMLError as exc:
        log.error(f"Could not parse {args.registry_yaml}: {exc}")
        return 1

    try:
        check_version(registry.get("version"), SUPPORTED_REGISTRY_VERSIONS, what=args.registry_yaml)
    except VersionMismatch as exc:
        log.error(str(exc))
        return 1

    content = render_codeowners(registry)

    if args.stdout:
        sys.stdout.write(content)
        return 0

    out_path = Path(args.output_path)
    if args.dry_run:
        log.info(f"[dry-run] would write CODEOWNERS to: {out_path}")
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    log.ok(f"Written: {out_path}")
    return 0
