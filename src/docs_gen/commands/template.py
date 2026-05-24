"""template — list and emit packaged doc templates.

Templates ship with the package and are accessible via the CLI so the
companion skill (and external callers) don't need to bundle their own
copies. Teams can override individual templates by pointing --template-dir
at a local directory with matching filenames; missing entries fall back
to the packaged version.

Usage:
    docs-gen template list
    docs-gen template show doc-templates.md
    docs-gen template show workflows/docs-health.yml --template-dir ./my-templates
"""

from __future__ import annotations

import argparse
import sys
from importlib.resources import files
from pathlib import Path

from docs_gen import log, template_path


def _packaged_templates() -> list[str]:
    """Return relative paths of every file under the packaged templates/ dir."""
    root = Path(str(files("docs_gen").joinpath("templates")))
    if not root.exists():
        return []
    return sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file()
    )


def _resolve(name: str, override_dir: Path | None) -> Path:
    """Find a template by name, checking the override dir first."""
    if override_dir is not None:
        candidate = override_dir / name
        if candidate.exists():
            return candidate
    # Fall back to package data.
    return template_path(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs-gen template",
        description="List or print the contents of packaged doc templates.",
    )
    parser.add_argument("--template-dir", default=None,
                        help="Override directory checked before packaged templates.")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="List available templates")
    p_show = sub.add_parser("show", help="Print a template's contents to stdout")
    p_show.add_argument("name", help="Template name (e.g., doc-templates.md or workflows/docs-health.yml)")

    args = parser.parse_args(argv)
    override = Path(args.template_dir) if args.template_dir else None
    if override is not None and not override.is_dir():
        log.error(f"--template-dir not found or not a directory: {override}")
        return 1

    if args.action == "list":
        names = set(_packaged_templates())
        if override is not None:
            for p in override.rglob("*"):
                if p.is_file():
                    names.add(str(p.relative_to(override)))
        for name in sorted(names):
            origin = "override" if override and (override / name).exists() else "packaged"
            print(f"{name}\t({origin})")
        return 0

    if args.action == "show":
        path = _resolve(args.name, override)
        if not path.exists():
            log.error(f"Template not found: {args.name}")
            return 1
        sys.stdout.write(path.read_text(encoding="utf-8"))
        return 0

    return 0
