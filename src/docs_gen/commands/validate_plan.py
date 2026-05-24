#!/usr/bin/env python3
"""
validate_plan.py — Verify that doc-plan.json is well-formed before downstream scripts use it.

Catches Claude's structural mistakes (missing fields, invalid dispositions, inconsistent
generate flags) early so build_registry.py and friends don't fail with cryptic errors.

Usage:
    python validate_plan.py <doc-plan.json>
    python validate_plan.py .docs-meta/doc-plan.json --doc-types ../doc-types.yaml

Exit codes:
    0 — plan is valid
    1 — plan has errors (must fix before continuing)
    2 — plan has warnings (review recommended)
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required. Install: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(1)


VALID_DISPOSITIONS = {
    "adopt", "augment", "refactor", "reclassify",
    "enroll", "generate", "out_of_scope",
}

# Per disposition: expected `generate` field value (None = either OK)
DISPOSITION_GENERATE_EXPECTED = {
    "adopt": False,
    "augment": True,
    "refactor": True,
    "reclassify": True,
    "enroll": False,
    "generate": True,
    "out_of_scope": False,
}

REQUIRED_FIELDS = {"filename", "disposition"}
RECOMMENDED_FIELDS = {"owns", "paths", "cadence"}


def load_doc_types(yaml_path: Path) -> set[str]:
    """Return set of canonical filenames defined in doc-types.yaml."""
    with open(yaml_path) as f:
        config = yaml.safe_load(f)
    return {dt["canonical_filename"] for dt in config["doc_types"]}


def validate_plan(plan: dict, known_canonical_names: set[str]) -> tuple[list[dict], list[dict]]:
    """
    Returns (errors, warnings). Errors block; warnings recommend review.
    """
    errors = []
    warnings = []

    # Top-level checks
    if "docs" not in plan or not isinstance(plan["docs"], list):
        errors.append({
            "level": "error",
            "where": "top-level",
            "message": "Missing or invalid 'docs' field — must be a list.",
        })
        return errors, warnings  # Can't continue without docs list

    if "project_name" not in plan:
        warnings.append({
            "level": "warning",
            "where": "top-level",
            "message": "Missing 'project_name' — will default to '[PROJECT]' in registry.",
        })

    seen_filenames = set()

    for idx, entry in enumerate(plan["docs"]):
        ctx = f"docs[{idx}]"

        # Type check
        if not isinstance(entry, dict):
            errors.append({"level": "error", "where": ctx, "message": "Entry must be an object."})
            continue

        # Required fields
        missing = REQUIRED_FIELDS - set(entry.keys())
        if missing:
            errors.append({
                "level": "error",
                "where": ctx,
                "message": f"Missing required field(s): {', '.join(sorted(missing))}",
            })
            continue

        filename = entry["filename"]
        ctx = f"docs[{idx}] ({filename})"

        # Duplicate filename
        if filename in seen_filenames:
            errors.append({
                "level": "error",
                "where": ctx,
                "message": f"Duplicate filename '{filename}' in plan.",
            })
        seen_filenames.add(filename)

        # Disposition validity
        disposition = entry.get("disposition", "")
        if disposition not in VALID_DISPOSITIONS:
            errors.append({
                "level": "error",
                "where": ctx,
                "message": f"Invalid disposition '{disposition}'. "
                           f"Valid: {', '.join(sorted(VALID_DISPOSITIONS))}",
            })
            continue

        # generate flag matches disposition
        expected_generate = DISPOSITION_GENERATE_EXPECTED.get(disposition)
        actual_generate = entry.get("generate")
        if expected_generate is not None and actual_generate is not None:
            if actual_generate != expected_generate:
                errors.append({
                    "level": "error",
                    "where": ctx,
                    "message": (
                        f"disposition='{disposition}' expects generate={expected_generate}, "
                        f"but plan has generate={actual_generate}."
                    ),
                })
        elif expected_generate is not None and actual_generate is None:
            warnings.append({
                "level": "warning",
                "where": ctx,
                "message": f"Missing 'generate' field. Inferred {expected_generate} from disposition '{disposition}'.",
            })

        # Custom flag consistency
        is_custom = entry.get("custom", False)
        is_canonical = filename in known_canonical_names
        if is_custom and is_canonical:
            warnings.append({
                "level": "warning",
                "where": ctx,
                "message": (
                    f"'{filename}' is a standard doc type but marked custom=true. "
                    "Did you mean to enroll a different file?"
                ),
            })
        elif not is_custom and not is_canonical:
            warnings.append({
                "level": "warning",
                "where": ctx,
                "message": (
                    f"'{filename}' isn't a standard doc type but custom=false. "
                    "Set custom=true if this is a team-specific doc to enroll."
                ),
            })

        # For non-adopt/enroll dispositions, existing_path shouldn't be required,
        # but for adopt/refactor/augment/reclassify it usually should be set
        if disposition in {"adopt", "augment", "refactor", "reclassify"}:
            if not entry.get("existing_path"):
                warnings.append({
                    "level": "warning",
                    "where": ctx,
                    "message": (
                        f"disposition='{disposition}' typically references an existing file. "
                        "Consider setting 'existing_path'."
                    ),
                })

        # Recommended fields
        missing_recommended = RECOMMENDED_FIELDS - set(entry.keys())
        if missing_recommended:
            warnings.append({
                "level": "warning",
                "where": ctx,
                "message": (
                    f"Missing recommended field(s): {', '.join(sorted(missing_recommended))}. "
                    "These power the registry and GitHub Action."
                ),
            })

        # Paths should be a list of strings
        if "paths" in entry:
            paths = entry["paths"]
            if not isinstance(paths, list):
                errors.append({
                    "level": "error",
                    "where": ctx,
                    "message": f"'paths' must be a list, got {type(paths).__name__}.",
                })
            elif not all(isinstance(p, str) for p in paths):
                errors.append({
                    "level": "error",
                    "where": ctx,
                    "message": "'paths' must be a list of strings.",
                })

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate doc-plan.json structure")
    parser.add_argument("plan_file", help="Path to doc-plan.json")
    parser.add_argument(
        "--doc-types",
        default=None,
        help="Path to doc-types.yaml (default: ../doc-types.yaml relative to this script)",
    )
    args = parser.parse_args(argv)

    plan_path = Path(args.plan_file)
    if not plan_path.exists():
        print(f"❌ File not found: {plan_path}", file=sys.stderr)
        return 1

    try:
        plan = json.loads(plan_path.read_text())
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}", file=sys.stderr)
        return 1

    if args.doc_types:
        doc_types_path = Path(args.doc_types)
    else:
        from docs_gen import config_path
        doc_types_path = config_path("doc-types.yaml")

    if not doc_types_path.exists():
        print(f"❌ doc-types.yaml not found at {doc_types_path}", file=sys.stderr)
        return 1

    known_canonical_names = load_doc_types(doc_types_path)
    print(f"🔍 Validating {plan_path} ({len(plan.get('docs', []))} docs)", file=sys.stderr)

    errors, warnings = validate_plan(plan, known_canonical_names)

    if errors:
        print(f"\n🔴 {len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - [{e['where']}] {e['message']}", file=sys.stderr)
    if warnings:
        print(f"\n🟡 {len(warnings)} warning(s):", file=sys.stderr)
        for w in warnings:
            print(f"  - [{w['where']}] {w['message']}", file=sys.stderr)

    if not errors and not warnings:
        print("\n✅ Plan is valid with no warnings.", file=sys.stderr)

    if errors:
        return 1
    elif warnings:
        return 2
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
