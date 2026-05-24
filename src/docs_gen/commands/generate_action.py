#!/usr/bin/env python3
"""
generate_action.py — Generate .github/workflows/docs-check.yml from docs-registry.yaml.

The registry is the single source of truth for path-to-doc mappings.
The GitHub Action is generated from it — never edit the action YAML directly.

Usage:
    python generate_action.py <docs-registry.yaml> <output_dir>
    python generate_action.py docs-registry.yaml .github/workflows
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required. Install with: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(1)

from docs_gen import SUPPORTED_REGISTRY_VERSIONS, VersionMismatch, check_version, log


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def glob_to_grep_pattern(glob: str) -> str:
    """
    Convert a glob-style path pattern into a grep -E compatible regex.

    Translation rules, applied to a tokenized form to avoid double-replacement:
      **      → matches any path segment(s), zero or more directories
      *       → matches any chars except /
      .       → literal dot
      other   → as-is
    """
    # Tokenize first: replace ** and * with sentinels before escaping other chars
    DOUBLESTAR = "\x00DOUBLESTAR\x00"
    STAR = "\x00STAR\x00"
    s = glob.replace("**", DOUBLESTAR).replace("*", STAR)
    # Escape regex specials (only . in practice for path globs)
    s = s.replace(".", r"\.")
    # Substitute sentinels with their regex equivalents
    s = s.replace(DOUBLESTAR, ".*")
    s = s.replace(STAR, "[^/]*")
    return s


def paths_to_pattern(paths: list[str]) -> str:
    """Combine multiple path globs into a single alternation regex."""
    return "|".join(glob_to_grep_pattern(p) for p in paths)


def generate_action_yaml(registry: dict, *, strict: bool = False) -> str:
    project = registry.get("project", "this project")
    docs = registry.get("docs", [])

    # Build check calls — each gets exactly 10 spaces of leading indent (inside `run: |`)
    check_lines = []
    custom_lines = []

    for doc in docs:
        paths = doc.get("paths", [])
        if not paths:
            continue
        pattern = paths_to_pattern(paths)
        if not pattern:
            continue
        filename = doc["file"]
        line = f'          check "{pattern}" "{filename}" "related paths changed"'
        if doc.get("custom"):
            custom_lines.append(line)
        else:
            check_lines.append(line)

    all_check_lines = check_lines[:]
    if custom_lines:
        all_check_lines.append("")
        all_check_lines.append("          # Custom docs enrolled by the team")
        all_check_lines.extend(custom_lines)

    check_block = "\n".join(all_check_lines) if all_check_lines else "          # No path mappings declared in registry"

    # Build mode-dependent fragments before the f-string so they can be
    # interpolated alongside the static blocks.
    mode_banner = "STRICT (fails the PR when docs aren't updated)" if strict else "soft (comments only)"
    if strict:
        strict_note = "> ⛔ **Strict mode**: this check fails until the docs listed above are updated in this PR."
        strict_fail_step = (
            "      - name: Fail when docs aren't updated\n"
            "        if: steps.map.outputs.flagged != ''\n"
            "        run: |\n"
            "          echo \"::error::Affected docs were not updated. Update them or remove the path mapping from docs-registry.yaml.\"\n"
            "          exit 1\n\n"
        )
    else:
        strict_note = "> This check never blocks merging — it's a prompt, not a gate."
        strict_fail_step = ""

    yaml_text = f"""# docs-check.yml
# ⚠️ Generated from docs-registry.yaml — do not edit directly.
# To update path mappings, edit docs-registry.yaml and re-run generate_action.py.
#
# Mode: {mode_banner}
# Project: {project}

name: Docs Check

on:
  pull_request:
    branches:
      - main

jobs:
  docs-check:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Get changed files
        id: changed
        run: |
          git diff --name-only origin/main...HEAD > /tmp/changed_files.txt
          echo "Changed files:"
          cat /tmp/changed_files.txt

      - name: Map changes to docs
        id: map
        run: |
          FLAGGED=""

          check() {{
            local pattern="$1"
            local doc="$2"
            local reason="$3"
            if grep -qE "$pattern" /tmp/changed_files.txt; then
              FLAGGED="${{FLAGGED}}\\n- [ ] \\`${{doc}}\\` — ${{reason}}"
            fi
          }}

{check_block}

          # Preserve multiline output for next step
          echo "flagged<<EOF" >> "$GITHUB_OUTPUT"
          printf "%b" "$FLAGGED" >> "$GITHUB_OUTPUT"
          echo "" >> "$GITHUB_OUTPUT"
          echo "EOF" >> "$GITHUB_OUTPUT"

      - name: Post PR comment
        if: steps.map.outputs.flagged != ''
        uses: actions/github-script@v7
        with:
          script: |
            const flagged = `${{{{ steps.map.outputs.flagged }}}}`;
            const body = [
              "## 📋 Docs Check",
              "",
              "These docs may be affected by this PR. Review each one and either update it or",
              "check it off to confirm it's still accurate.",
              "",
              flagged,
              "",
              "{strict_note}",
              "> Log your review in [DOCS_AUDIT_LOG.md](../../DOCS_AUDIT_LOG.md)."
            ].join("\\n");

            await github.rest.issues.createComment({{
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body
            }});

{strict_fail_step}      - name: No docs flagged
        if: steps.map.outputs.flagged == ''
        run: echo "✅ No docs flagged for this PR."
"""
    return yaml_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docs-gen generate-action",
                                     description="Generate .github/workflows/docs-check.yml from docs-registry.yaml")
    parser.add_argument("registry_yaml", help="Path to docs-registry.yaml")
    parser.add_argument("output_dir", help="Directory for the workflow file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print would-write paths without modifying the filesystem")
    parser.add_argument("--audit-log", default=None,
                        help="If set, append an entry to this audit log after regeneration")
    parser.add_argument("--reviewer", default="[automated]",
                        help="Reviewer name to record in the audit entry (default: [automated])")
    parser.add_argument("--strict", action="store_true",
                        help="Emit a workflow that fails the PR when affected docs aren't updated (default: comment only)")
    args = parser.parse_args(argv)

    registry_path = args.registry_yaml
    output_dir = Path(args.output_dir)

    try:
        registry = load_yaml(registry_path)
    except FileNotFoundError:
        log.error(f"Registry not found: {registry_path}")
        return 1
    except yaml.YAMLError as exc:
        log.error(f"Could not parse {registry_path}: {exc}")
        return 1

    try:
        check_version(registry.get("version"), SUPPORTED_REGISTRY_VERSIONS, what=registry_path)
    except VersionMismatch as exc:
        log.error(str(exc))
        return 1

    action_yaml = generate_action_yaml(registry, strict=args.strict)
    out_path = output_dir / "docs-check.yml"

    if args.dry_run:
        log.info(f"[dry-run] would create directory: {output_dir}")
        log.info(f"[dry-run] would write: {out_path}")
        if args.audit_log:
            log.info(f"[dry-run] would append audit entry to: {args.audit_log}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(action_yaml)
    log.ok(f"Written: {out_path}")

    with_paths = sum(1 for d in registry.get("docs", []) if d.get("paths"))
    without_paths = sum(1 for d in registry.get("docs", []) if not d.get("paths"))
    log.info(f"Docs with path mappings: {with_paths}")
    log.info(f"Docs without mappings (no code paths declared): {without_paths}")

    if args.audit_log:
        from docs_gen.commands.audit import append_entry
        append_entry(
            Path(args.audit_log),
            docs=".github/workflows/docs-check.yml",
            change="Regenerated docs-check.yml from docs-registry.yaml",
            trigger="generate-action CLI",
            reviewer=args.reviewer,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
