#!/usr/bin/env python3
"""
build_registry.py — Generate docs-registry.yaml and DOCS_REGISTRY.md from doc-plan.json.

docs-registry.yaml is the machine-readable single source of truth.
DOCS_REGISTRY.md is generated from it — never edit the markdown directly.

Usage:
    python build_registry.py <doc_plan.json> <output_dir>
    python build_registry.py doc-plan.json .
"""

import argparse
import json
import sys
import textwrap
from datetime import date
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from docs_gen import log


def load_doc_plan(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _extract_summary(content: str, max_chars: int = 240) -> str:
    """Pull a one-paragraph summary from a markdown doc.

    Strategy: skip leading blank lines and the first H1 heading. Take the
    first non-empty paragraph, collapse whitespace, truncate to max_chars
    at a word boundary. Returns "" if no usable content found.
    """
    if not content:
        return ""
    lines = content.splitlines()
    i = 0
    # Skip leading blanks
    while i < len(lines) and not lines[i].strip():
        i += 1
    # Skip a single H1 heading line, if present.
    if i < len(lines) and lines[i].lstrip().startswith("# "):
        i += 1
    # Skip blanks between H1 and the first paragraph.
    while i < len(lines) and not lines[i].strip():
        i += 1
    # Collect the next non-blank block, skipping any subheadings.
    para_lines: list[str] = []
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            if para_lines:
                break
            i += 1
            continue
        if line.lstrip().startswith(("#", "```", "|", "<!--", ">", "- ", "* ")):
            i += 1
            if para_lines:
                break
            continue
        para_lines.append(line.strip())
        i += 1
    text = " ".join(para_lines).strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return truncated + "…"


def _resolve_summary(entry: dict, repo_root: Path | None) -> str:
    """Pick the best summary for a doc-plan entry.

    Priority: explicit `summary` in the plan → auto-extract from the doc
    file if it already exists on disk → empty string.
    """
    declared = entry.get("summary")
    if declared:
        return str(declared).strip()
    if repo_root is None:
        return ""
    candidates = []
    if entry.get("existing_path"):
        candidates.append(repo_root / entry["existing_path"])
    candidates.append(repo_root / entry["filename"])
    for path in candidates:
        if path.is_file():
            try:
                return _extract_summary(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return ""


def build_registry_yaml(doc_plan: dict, repo_root: Path | None = None) -> dict:
    """Build the registry data structure from doc-plan.json.

    `repo_root` is used to auto-extract `summary` fields from existing
    doc files. When None, summaries are taken only from explicit `summary`
    fields in the plan.
    """
    # Normalize disposition (verb) → origin (state/noun) for the registry
    origin_map = {
        "generate": "generated",
        "adopt": "adopted",
        "augment": "augmented",
        "refactor": "refactored",
        "enroll": "enrolled-custom",
        "reclassify": "reclassified",
    }

    registry = {
        "version": 1,
        "project": doc_plan.get("project_name", "[PROJECT]"),
        "generated_at": str(date.today()),
        "docs": [],
    }

    for entry in doc_plan.get("docs", []):
        if entry.get("disposition") in ("out_of_scope",):
            continue

        disposition = entry.get("disposition", "generate")
        reg_entry = {
            "file": entry["filename"],
            "owns": entry.get("owns", []),
            "paths": entry.get("paths", []),
            "origin": origin_map.get(disposition, disposition),
            "cadence": entry.get("cadence", "on-change"),
            "custom": entry.get("custom", False),
            "owners": entry.get("owners", []),
            "summary": _resolve_summary(entry, repo_root),
            "last_reviewed": str(date.today()),
            "reviewer": "",
        }
        registry["docs"].append(reg_entry)

    return registry


def render_yaml(data: dict) -> str:
    """Render registry as YAML, with or without pyyaml."""
    if HAS_YAML:
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Minimal hand-rolled YAML for environments without pyyaml
    lines = []
    lines.append(f"version: {data['version']}")
    lines.append(f"project: \"{data['project']}\"")
    lines.append(f"generated_at: \"{data['generated_at']}\"")
    lines.append("docs:")
    for doc in data["docs"]:
        lines.append(f"  - file: {doc['file']}")
        lines.append(f"    origin: {doc['origin']}")
        lines.append(f"    cadence: {doc['cadence']}")
        lines.append(f"    custom: {'true' if doc['custom'] else 'false'}")
        lines.append(f"    last_reviewed: \"{doc['last_reviewed']}\"")
        lines.append(f"    reviewer: \"{doc['reviewer']}\"")
        if doc.get("summary"):
            lines.append(f"    summary: \"{doc['summary'].replace(chr(34), chr(92) + chr(34))}\"")
        if doc["owns"]:
            lines.append("    owns:")
            for item in doc["owns"]:
                lines.append(f"      - \"{item}\"")
        else:
            lines.append("    owns: []")
        if doc["paths"]:
            lines.append("    paths:")
            for p in doc["paths"]:
                lines.append(f"      - \"{p}\"")
        else:
            lines.append("    paths: []")
        owners = doc.get("owners") or []
        if owners:
            lines.append("    owners:")
            for o in owners:
                lines.append(f"      - \"{o}\"")
        else:
            lines.append("    owners: []")
    return "\n".join(lines) + "\n"


def _propose_authoritative(subject: str, kind: str, candidates: list[str], docs_index: dict[str, dict]) -> str | None:
    """Pick the most likely authoritative doc for a given subject.

    Heuristic:
      - For code paths: the candidate whose `paths` contains a more specific
        (longer) match for the subject wins; ties broken by the doc whose
        `owns` topics share words with the path basename.
      - For ownership topics: the candidate whose `owns` contains the exact
        subject string (case-insensitive) wins; ties broken by file name
        alphabetic order so the choice is stable.
    Returns the proposed filename, or None if the heuristic can't decide.
    """
    if not candidates:
        return None

    if kind == "code_path":
        best: tuple[int, str] | None = None
        for c in candidates:
            paths = docs_index.get(c, {}).get("paths", [])
            specificity = max((len(p) for p in paths if p == subject), default=0)
            if best is None or specificity > best[0]:
                best = (specificity, c)
        if best and best[0] > 0:
            return best[1]
        return sorted(candidates)[0]

    # ownership_topic
    subject_norm = subject.lower().strip()
    exact = [c for c in candidates if subject_norm in
             {t.lower().strip() for t in docs_index.get(c, {}).get("owns", [])}]
    if exact:
        return sorted(exact)[0]
    return sorted(candidates)[0]


def detect_overlaps(docs: list[dict]) -> list[dict]:
    """
    Find docs that share code paths or ownership topics — these are contradiction risks.

    Returns a list of {subject, type, docs, proposed_authoritative} entries for the
    cross-reference table.
    """
    from collections import defaultdict

    docs_index = {d["file"]: d for d in docs}

    path_to_docs = defaultdict(list)
    for d in docs:
        for p in d.get("paths", []):
            path_to_docs[p].append(d["file"])

    topic_to_docs = defaultdict(list)
    for d in docs:
        for t in d.get("owns", []):
            topic_to_docs[t.lower().strip()].append(d["file"])

    overlaps = []
    for path, files in sorted(path_to_docs.items()):
        if len(files) > 1:
            overlaps.append({
                "subject": path,
                "type": "code_path",
                "docs": files,
                "proposed_authoritative": _propose_authoritative(path, "code_path", files, docs_index),
            })
    for topic, files in sorted(topic_to_docs.items()):
        if len(files) > 1:
            overlaps.append({
                "subject": topic,
                "type": "ownership_topic",
                "docs": files,
                "proposed_authoritative": _propose_authoritative(topic, "ownership_topic", files, docs_index),
            })
    return overlaps


def render_markdown(registry: dict) -> str:
    """Render DOCS_REGISTRY.md from registry data. Do not edit this file directly."""
    today = registry["generated_at"]
    project = registry["project"]
    docs = registry["docs"]

    rows = []
    for d in docs:
        owns = ", ".join(d["owns"]) if d["owns"] else "—"
        paths = "<br>".join(f"`{p}`" for p in d["paths"]) if d["paths"] else "—"
        cadence = d["cadence"]
        origin = d["origin"]
        last_reviewed = d["last_reviewed"] or "—"
        reviewer = d["reviewer"] or "—"
        flag = " 🌐" if d.get("custom") else ""
        rows.append(
            f"| `{d['file']}`{flag} | {owns} | {paths} | {origin} | {cadence} | {last_reviewed} | {reviewer} |"
        )
    ownership_table = "\n".join(rows)

    # Auto-detect cross-references
    overlaps = detect_overlaps(docs)
    if overlaps:
        xref_rows = []
        for o in overlaps:
            type_label = "code path" if o["type"] == "code_path" else "topic"
            subject = f"`{o['subject']}`" if o["type"] == "code_path" else o["subject"]
            docs_list = ", ".join(f"`{d}`" for d in o["docs"])
            proposed = o.get("proposed_authoritative")
            if proposed:
                authoritative_cell = f"`{proposed}` *(proposed — confirm or override)*"
            else:
                authoritative_cell = "*[designate authoritative doc]*"
            xref_rows.append(
                f"| {subject} ({type_label}) | {docs_list} | {authoritative_cell} |"
            )
        xref_body = "\n".join(xref_rows)
        xref_intro = (
            "Auto-detected overlaps between docs. For each row, confirm or override the "
            "proposed authoritative source — other docs should link to it rather than restate."
        )
    else:
        xref_body = "| *(No overlaps detected. Add manually if you find any.)* | | |"
        xref_intro = (
            "Topics that appear in more than one doc are contradiction risks. "
            "None detected from path/ownership analysis — add manually if you find any."
        )

    out = []
    out.append(f"# Docs Registry — {project}")
    out.append("")
    out.append("> ⚠️ This file is generated from `docs-registry.yaml`. Do not edit it directly.")
    out.append("> To update, edit `docs-registry.yaml` and re-run `build_registry.py`.")
    out.append("")
    out.append(f"Generated: {today}")
    out.append("")
    out.append("## Ownership Map")
    out.append("")
    out.append("🌐 = custom doc enrolled by team")
    out.append("")
    out.append("| Doc | Owns (source of truth for...) | Maps to code paths | Origin | Cadence | Last Reviewed | Reviewer |")
    out.append("|-----|------------------------------|--------------------|--------|---------|--------------|----------|")
    out.append(ownership_table)
    out.append("")
    out.append("## Cross-Reference Table")
    out.append("")
    out.append(xref_intro)
    out.append("")
    out.append("| Subject | Docs that mention it | Authoritative doc |")
    out.append("|---------|---------------------|-------------------|")
    out.append(xref_body)
    out.append("")
    out.append("## Doc Summaries")
    out.append("")
    out.append("Short descriptions to help humans and agents pick the right doc to read.")
    out.append("Summaries are auto-extracted from each doc's first paragraph (or set in the plan).")
    out.append("")
    any_summary = False
    for d in docs:
        summary = (d.get("summary") or "").strip()
        if not summary:
            continue
        any_summary = True
        out.append(f"- **`{d['file']}`** — {summary}")
    if not any_summary:
        out.append("- *(No summaries yet — write the first paragraph of each doc and re-run `build-registry`.)*")
    out.append("")

    owners_rows = [d for d in docs if d.get("owners")]
    if owners_rows:
        out.append("## Doc Owners")
        out.append("")
        out.append("Reviewers responsible for each doc. Exported to `.github/CODEOWNERS` via `docs-gen codeowners`.")
        out.append("")
        out.append("| Doc | Owners |")
        out.append("|-----|--------|")
        for d in owners_rows:
            owners_cell = ", ".join(d["owners"])
            out.append(f"| `{d['file']}` | {owners_cell} |")
        out.append("")

    out.append("## Review Cadences")
    out.append("")
    out.append("| Cadence | Docs |")
    out.append("|---------|------|")
    out.append("| On every relevant PR | *(auto-flagged by docs-check.yml)* |")
    out.append("| On architectural changes | `ARCHITECTURE.md`, `DECISIONS.md` |")
    out.append("| Quarterly | `ONBOARDING.md`, `CONTRIBUTING.md` |")
    out.append("| Ongoing | `GOTCHAS.md` |")
    out.append("| As declared | *(custom docs per their cadence above)* |")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docs-gen build-registry",
                                     description="Generate docs-registry.yaml and DOCS_REGISTRY.md from doc-plan.json")
    parser.add_argument("doc_plan", help="Path to doc-plan.json")
    parser.add_argument("output_dir", help="Directory to write registry files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print would-write paths without modifying the filesystem")
    parser.add_argument("--audit-log", default=None,
                        help="If set, append an entry to this audit log after regeneration")
    parser.add_argument("--reviewer", default="[automated]",
                        help="Reviewer name to record in the audit entry (default: [automated])")
    args = parser.parse_args(argv)

    doc_plan_path = args.doc_plan
    output_dir = Path(args.output_dir)

    try:
        doc_plan = load_doc_plan(doc_plan_path)
    except FileNotFoundError:
        log.error(f"doc-plan not found: {doc_plan_path}")
        return 1
    except json.JSONDecodeError as exc:
        log.error(f"doc-plan is not valid JSON ({doc_plan_path}): {exc}")
        return 1

    # When summarizing, look for docs next to the output dir (the registry's home).
    registry = build_registry_yaml(doc_plan, repo_root=output_dir.resolve())
    yaml_path = output_dir / "docs-registry.yaml"
    md_path = output_dir / "DOCS_REGISTRY.md"

    if args.dry_run:
        log.info(f"[dry-run] would create directory: {output_dir}")
        log.info(f"[dry-run] would write: {yaml_path}")
        log.info(f"[dry-run] would write: {md_path}")
        if args.audit_log:
            log.info(f"[dry-run] would append audit entry to: {args.audit_log}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(render_yaml(registry))
    log.ok(f"Written: {yaml_path}")
    md_path.write_text(render_markdown(registry))
    log.ok(f"Written: {md_path}")

    if args.audit_log:
        from docs_gen.commands.audit import append_entry
        append_entry(
            Path(args.audit_log),
            docs="docs-registry.yaml, DOCS_REGISTRY.md",
            change="Regenerated registry from doc-plan.json",
            trigger="build-registry CLI",
            reviewer=args.reviewer,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
