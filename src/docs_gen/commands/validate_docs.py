#!/usr/bin/env python3
"""
validate_docs.py — Detect contradictions and drift across documentation files.

Runs three passes:
  1. Heuristic checks (fast, no LLM) — duplicate headers, env vars in multiple docs,
     conflicting version numbers.
  2. Semantic claim extraction — for each category defined in claim-categories.yaml,
     detect which named choices appear in each doc, using a dominant-value heuristic
     to avoid false positives when alternatives are mentioned in passing.
  3. Semantic summary — extracts key facts per doc for an LLM's deeper review.

Status messages → stderr. JSON report → stdout (or --output file).

Usage:
    python validate_docs.py <doc1.md> [doc2.md ...] [--output report.json]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

try:
    import yaml
except ImportError:
    print("❌ pyyaml required. Install: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(1)

from docs_gen import (
    SUPPORTED_CONFIG_VERSIONS,
    VersionMismatch,
    check_version,
    config_path,
    log,
)


def load_claim_categories(path: Path | None = None) -> dict:
    """Load and normalize the claim categories config."""
    if path is None:
        path = config_path("claim-categories.yaml")
    with open(path) as f:
        config = yaml.safe_load(f)
    check_version(config.get("version"), SUPPORTED_CONFIG_VERSIONS, what=str(path))
    result = {}
    for cat in config["categories"]:
        result[cat["name"]] = {
            "exclusive": cat["exclusive"],
            "patterns": [(p["pattern"], p["label"]) for p in cat["patterns"]],
        }
    return result


# ── Heuristic checks ────────────────────────────────────────────────────────

def extract_headers(content: str) -> list[str]:
    return re.findall(r"^#{1,3}\s+(.+)$", content, re.MULTILINE)


def extract_code_blocks(content: str) -> list[str]:
    return re.findall(r"```[\w]*\n(.*?)```", content, re.DOTALL)


def extract_env_vars(content: str) -> list[str]:
    """Find env var names mentioned (ALL_CAPS patterns that look like vars)."""
    return list(set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", content)))


def extract_version_mentions(content: str) -> list[str]:
    """Find version strings like 'Node 20', 'Python 3.11', 'v2.1', etc."""
    patterns = [
        r"Node(?:\.js)?\s+(?:>=\s*)?([\d]+(?:\.[\d]+)*)",
        r"Python\s+([\d]+(?:\.[\d]+)*)",
        r"pnpm\s+([\d]+(?:\.[\d]+)*)",
        r"\bv([\d]+\.[\d]+(?:\.[\d]+)?)\b",
    ]
    found = []
    for p in patterns:
        found.extend(re.findall(p, content, re.IGNORECASE))
    return found


def check_duplicate_headers(docs: dict[str, str]) -> list[dict]:
    """Flag identical section headers appearing in multiple docs."""
    header_map = defaultdict(list)
    for filename, content in docs.items():
        for h in extract_headers(content):
            normalized = h.strip().lower()
            header_map[normalized].append(filename)

    issues = []
    # Only flag substantive headers (not "Overview", "Usage", etc. which are universal)
    skip_generic = {"overview", "usage", "installation", "getting started", "contributing",
                    "license", "table of contents", "introduction", "references", "notes"}
    for header, files in header_map.items():
        if len(files) > 1 and header not in skip_generic:
            issues.append({
                "type": "duplicate_header",
                "severity": "low",
                "header": header,
                "found_in": files,
                "message": f'Section "{header}" appears in {len(files)} docs — '
                           f"may indicate overlapping scope.",
            })
    return issues


def check_env_var_conflicts(docs: dict[str, str]) -> list[dict]:
    """Flag env vars defined (with backticks) in more than one doc."""
    var_doc_map = defaultdict(list)
    for filename, content in docs.items():
        # Only look for vars that appear near definition-like context
        defining_pattern = re.findall(r"`([A-Z][A-Z0-9_]{2,})`", content)
        for var in set(defining_pattern):
            var_doc_map[var].append(filename)

    issues = []
    for var, files in var_doc_map.items():
        if len(files) > 1:
            # Only flag if one of the docs is ENVIRONMENT.md (the owner)
            if any("ENVIRONMENT" in f.upper() for f in files):
                others = [f for f in files if "ENVIRONMENT" not in f.upper()]
                if others:
                    issues.append({
                        "type": "env_var_duplication",
                        "severity": "medium",
                        "var": var,
                        "authoritative": next(f for f in files if "ENVIRONMENT" in f.upper()),
                        "also_in": others,
                        "message": f"`{var}` is defined in ENVIRONMENT.md but also referenced "
                                   f"in {others}. Ensure other docs link to ENVIRONMENT.md "
                                   f"rather than redefining the var.",
                    })
    return issues


def check_version_conflicts(docs: dict[str, str]) -> list[dict]:
    """Flag conflicting version numbers for the same technology."""
    tech_versions = defaultdict(lambda: defaultdict(list))
    tech_patterns = {
        "Node.js": r"Node(?:\.js)?\s+(?:>=\s*)?([\d]+(?:\.[\d]+)*)",
        "Python":  r"Python\s+([\d]+(?:\.[\d]+)*)",
        "pnpm":    r"pnpm\s+([\d]+(?:\.[\d]+)*)",
    }
    for filename, content in docs.items():
        for tech, pattern in tech_patterns.items():
            matches = re.findall(pattern, content, re.IGNORECASE)
            for version in set(matches):
                tech_versions[tech][version].append(filename)

    issues = []
    for tech, versions in tech_versions.items():
        if len(versions) > 1:
            issues.append({
                "type": "version_conflict",
                "severity": "high",
                "technology": tech,
                "versions_found": {v: files for v, files in versions.items()},
                "message": f"Conflicting {tech} versions found across docs: "
                           + ", ".join(f"{v} (in {', '.join(f)})" for v, f in versions.items()),
            })
    return issues


# ── Semantic claim extraction ────────────────────────────────────────────────
# Categories defined in claim-categories.yaml (sibling to scripts/).
# Loaded at runtime by load_claim_categories().


def extract_claims(content: str, categories: dict) -> dict[str, dict]:
    """
    Extract category → {dominant: str|None, all_mentioned: dict[str, int]} for a doc.

    For exclusive categories, the 'dominant' value is the one mentioned significantly
    more than alternatives (count >= 2× the runner-up). If no value clearly dominates,
    dominant is None — meaning the doc discusses multiple options without committing,
    which is common in ADRs and architecture comparisons.

    For non-exclusive categories, dominant is always None — multiple values are fine.
    """
    claims = {}
    for category, config in categories.items():
        value_counts = {}
        for pattern, label in config["patterns"]:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                value_counts[label] = len(matches)

        if not value_counts:
            continue

        sorted_values = sorted(value_counts.items(), key=lambda kv: -kv[1])
        dominant = None
        if config["exclusive"]:
            if len(sorted_values) == 1:
                dominant = sorted_values[0][0]
            elif sorted_values[0][1] >= sorted_values[1][1] * 2:
                dominant = sorted_values[0][0]

        claims[category] = {
            "dominant": dominant,
            "all_mentioned": dict(value_counts),
        }
    return claims


def check_claim_conflicts(docs: dict[str, str], categories: dict) -> tuple[list[dict], dict[str, dict]]:
    """
    Extract claims per doc and flag conflicts where different docs have different
    DOMINANT values in mutually-exclusive categories.

    Returns (issues, per_doc_claims).
    """
    per_doc_claims = {filename: extract_claims(content, categories) for filename, content in docs.items()}

    category_dominants = defaultdict(lambda: defaultdict(list))
    for filename, claims in per_doc_claims.items():
        for category, info in claims.items():
            if not categories[category]["exclusive"]:
                continue
            if info["dominant"] is not None:
                category_dominants[category][info["dominant"]].append(filename)

    issues = []
    for category, dominants in category_dominants.items():
        if len(dominants) <= 1:
            continue

        issues.append({
            "type": "claim_conflict",
            "severity": "high",
            "category": category,
            "dominants_per_doc": {v: files for v, files in dominants.items()},
            "message": (
                f"Conflicting dominant {category} across docs: "
                + "; ".join(f"'{v}' in {', '.join(files)}" for v, files in dominants.items())
                + ". Category is mutually exclusive — only one should be correct."
            ),
        })

    return issues, per_doc_claims


def build_semantic_summary(docs: dict[str, str]) -> dict[str, dict]:
    """
    Extract key facts from each doc so an LLM can review for deeper contradictions.
    Returns a dict of filename → {headers, env_vars, version_mentions, word_count}.
    """
    summary = {}
    for filename, content in docs.items():
        summary[filename] = {
            "word_count": len(content.split()),
            "headers": extract_headers(content),
            "env_vars_mentioned": extract_env_vars(content),
            "version_mentions": extract_version_mentions(content),
            "first_500_chars": content[:500],
        }
    return summary


# ── Main ────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate docs for contradictions and drift")
    parser.add_argument("docs", nargs="+", help="Markdown files to validate")
    parser.add_argument("--output", default=None, help="Write JSON report to this path")
    parser.add_argument("--claim-categories", default=None,
                        help="Override path to claim-categories.yaml (default: packaged config)")
    args = parser.parse_args(argv)

    docs: dict[str, str] = {}
    for path_str in args.docs:
        path = Path(path_str)
        if not path.exists():
            log.warn(f"Skipping {path_str} — file not found")
            continue
        try:
            docs[path.name] = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            log.warn(f"Skipping {path_str} — could not read: {exc}")

    if not docs:
        log.error("No readable docs found.")
        return 1

    log.info(f"Validating {len(docs)} docs: {', '.join(docs.keys())}")

    try:
        cat_path = Path(args.claim_categories) if args.claim_categories else None
        categories = load_claim_categories(cat_path)
    except FileNotFoundError as exc:
        log.error(f"Could not find claim categories file: {exc}")
        return 1
    except yaml.YAMLError as exc:
        log.error(f"Could not parse claim categories file: {exc}")
        return 1
    except VersionMismatch as exc:
        log.error(str(exc))
        return 1

    issues = []
    issues.extend(check_duplicate_headers(docs))
    issues.extend(check_env_var_conflicts(docs))
    issues.extend(check_version_conflicts(docs))
    claim_issues, per_doc_claims = check_claim_conflicts(docs, categories)
    issues.extend(claim_issues)

    high   = [i for i in issues if i["severity"] == "high"]
    medium = [i for i in issues if i["severity"] == "medium"]
    low    = [i for i in issues if i["severity"] == "low"]

    assistant_instructions = (
        "Review the issues above, the extracted_claims per doc, and the "
        "semantic_summary. Heuristics catch surface-level contradictions and "
        "claim conflicts in mutually-exclusive categories (database, auth, etc.). "
        "Look for deeper contradictions that named-entity matching can't catch — "
        "e.g., two docs describing the same flow differently, or conflicting "
        "claims phrased in non-standard ways. Flag any you find and resolve them "
        "before finalizing."
    )
    report = {
        "docs_checked": list(docs.keys()),
        "issue_count": len(issues),
        "summary": {"high": len(high), "medium": len(medium), "low": len(low)},
        "issues": issues,
        "extracted_claims": per_doc_claims,
        "semantic_summary": build_semantic_summary(docs),
        "assistant_instructions": assistant_instructions,
        # Deprecated: removed in a future release. Use assistant_instructions instead.
        "claude_instructions": assistant_instructions,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        log.ok(f"Report written to {args.output}")
    else:
        print(json.dumps(report, indent=2))

    if high:
        log.error(f"{len(high)} high-severity issue(s) found — resolve before finalizing.")
        return 2
    elif medium:
        log.warn(f"{len(medium)} medium-severity issue(s) found — review recommended.")
        return 1
    else:
        log.ok(f"No high/medium issues found. {len(low)} low-severity note(s).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
