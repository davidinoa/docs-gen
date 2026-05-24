#!/usr/bin/env python3
"""
assess_specs.py — Evaluate completeness of an existing SPECS.md (or equivalent).

Approach:
  Primary signal: section headers that map to each dimension, weighted by content depth.
  Secondary signal: keyword density inside each section (catches well-covered dimensions
  that use unconventional section names).

Status messages go to stderr; JSON report goes to stdout. Safe to pipe.

Usage:
    python assess_specs.py <spec_file>
    python assess_specs.py SPECS.md --output report.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ── Dimension definitions ────────────────────────────────────────────────────

DIMENSIONS = {
    "purpose": {
        "label": "Purpose & Goals",
        "description": "Why the project exists, what problem it solves, what success looks like",
        "header_patterns": [
            r"purpose", r"goals?", r"objectives?", r"mission", r"vision",
            r"problem", r"motivation", r"why\b", r"success criteri",
            r"kpis?", r"metrics?", r"outcomes?", r"overview",
        ],
        "body_keywords": [
            "goal", "objective", "purpose", "problem", "why", "mission",
            "success", "kpi", "metric", "outcome", "solve",
        ],
        "questions": [
            "What problem does this project solve?",
            "What does success look like — how will you know it's working?",
            "Are there specific KPIs or metrics to hit?",
        ],
    },
    "users": {
        "label": "Users & Personas",
        "description": "Who uses this, their needs, their technical level",
        "header_patterns": [
            r"users?", r"personas?", r"audience", r"customers?",
            r"stakeholders?", r"actors?", r"who\b",
        ],
        "body_keywords": [
            "user", "persona", "audience", "customer", "stakeholder",
            "developer", "admin", "operator", "consumer",
        ],
        "questions": [
            "Who are the primary users of this system?",
            "Are there multiple user types or roles with different needs?",
            "What's their technical level?",
        ],
    },
    "features": {
        "label": "Functional Requirements",
        "description": "What the system must do — core features, user stories, requirements",
        "header_patterns": [
            r"functional", r"features?", r"requirements?", r"user stor",
            r"use cases?", r"capabilities", r"functionality",
            r"core (functionality|features|requirements)", r"mvp",
            r"must[- ]have", r"scope\b",
        ],
        "body_keywords": [
            "feature", "requirement", "must", "shall", "should",
            "user story", "use case", "functionality", "capability",
        ],
        "questions": [
            "What are the core features — what must the system do?",
            "Are there specific user flows or interactions to support?",
            "What's the MVP vs. later phases?",
        ],
    },
    "non_functional": {
        "label": "Non-Functional Requirements",
        "description": "Performance, security, availability, scalability, accessibility",
        "header_patterns": [
            r"non[- ]functional", r"performance", r"security",
            r"availability", r"scalability", r"reliability",
            r"accessibility", r"compliance", r"quality attributes",
            r"sla\b", r"slo\b",
        ],
        "body_keywords": [
            "performance", "security", "scalability", "availability",
            "uptime", "latency", "throughput", "compliance",
            "accessibility", "wcag", "sla", "encryption",
        ],
        "questions": [
            "Performance expectations? (response time, scale, load)",
            "Security requirements? (auth model, data privacy, compliance)",
            "Any availability or uptime expectations?",
            "Accessibility requirements?",
        ],
    },
    "constraints": {
        "label": "Constraints & Boundaries",
        "description": "Tech mandates, budget, timeline, out-of-scope, dependencies",
        "header_patterns": [
            r"constraints?", r"limitations?", r"out[- ]of[- ]scope",
            r"not[- ]in[- ]scope", r"boundaries", r"dependencies",
            r"assumptions", r"prerequisites", r"deadline",
            r"timeline", r"budget",
        ],
        "body_keywords": [
            "constraint", "limitation", "out of scope", "excluded",
            "deadline", "budget", "must not", "cannot", "restriction",
            "dependency", "mandated", "required to use",
        ],
        "questions": [
            "What is explicitly out of scope?",
            "Are there tech stack mandates or constraints?",
            "Any timeline, budget, or compliance constraints?",
            "Locked-in dependencies or third-party services?",
        ],
    },
    "decisions": {
        "label": "Decisions Already Made",
        "description": "Architectural or product decisions locked in",
        "header_patterns": [
            r"decisions?( already)?( made)?", r"adrs?",
            r"key (decisions|choices)", r"technical decisions",
            r"chosen", r"locked[- ]in",
        ],
        "body_keywords": [
            "decision", "chose", "chosen", "decided", "adopted",
            "will use", "rationale", "trade-off", "alternative",
        ],
        "questions": [
            "What architectural or product decisions are already locked in?",
            "Are there decisions that shouldn't be relitigated?",
        ],
    },
}


# ── Section parsing ──────────────────────────────────────────────────────────

def parse_sections(content: str) -> list[dict]:
    """Split markdown into sections by ## headers."""
    sections = []
    lines = content.split("\n")
    current = {"header": "(intro)", "level": 0, "body": []}

    for line in lines:
        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            if current["body"] or current["header"] != "(intro)":
                current["body_text"] = "\n".join(current["body"]).strip()
                current["word_count"] = len(current["body_text"].split())
                sections.append(current)
            level = len(m.group(1))
            current = {"header": m.group(2).strip(), "level": level, "body": []}
        else:
            current["body"].append(line)

    current["body_text"] = "\n".join(current["body"]).strip()
    current["word_count"] = len(current["body_text"].split())
    sections.append(current)
    return sections


def match_header(header: str, patterns: list[str]) -> bool:
    """Check if a section header matches any of the dimension's patterns."""
    h = header.lower()
    return any(re.search(p, h) for p in patterns)


def score_dimension(sections: list[dict], dim: dict, full_content: str) -> dict:
    """
    Score a dimension based on:
      1. Whether a matching section exists (primary signal)
      2. How much content is under it INCLUDING subsections (depth)
      3. Body keyword density across the doc (secondary signal)

    Skips H1 sections (those are doc titles, not content sections).
    Avoids double-counting nested matches by only including each section once.
    """
    matching_indices = []
    for i, s in enumerate(sections):
        if s["level"] == 1:
            continue  # Skip H1 — that's the doc title, not a section
        if match_header(s["header"], dim["header_patterns"]):
            matching_indices.append(i)

    # For each matched section, compute word count including subsections
    # (sections that follow it at deeper levels until we hit one at equal/shallower level)
    counted_indices = set()
    total_section_words = 0
    matching_section_names = []

    for idx in matching_indices:
        if idx in counted_indices:
            continue  # Already counted as a subsection of an earlier match
        parent_level = sections[idx]["level"]
        matching_section_names.append(sections[idx]["header"])

        # Count this section and all subsequent deeper-level sections
        total_section_words += sections[idx]["word_count"]
        counted_indices.add(idx)
        j = idx + 1
        while j < len(sections) and sections[j]["level"] > parent_level:
            total_section_words += sections[j]["word_count"]
            counted_indices.add(j)
            j += 1

    content_lower = full_content.lower()
    keyword_hits = sum(1 for kw in dim["body_keywords"] if kw in content_lower)

    # Decision rules
    if matching_section_names and total_section_words >= 50:
        coverage = "good"
    elif matching_section_names and total_section_words >= 15:
        coverage = "thin"
    elif keyword_hits >= 5:
        coverage = "thin"
    else:
        coverage = "missing"

    return {
        "coverage": coverage,
        "matching_sections": matching_section_names,
        "section_word_count": total_section_words,
        "keyword_hits": keyword_hits,
    }


# ── Main assessment ──────────────────────────────────────────────────────────

def assess_spec(content: str) -> dict:
    sections = parse_sections(content)
    word_count = len(content.split())
    line_count = len(content.splitlines())

    dimension_results = {}
    for dim_key, dim in DIMENSIONS.items():
        score = score_dimension(sections, dim, content)
        dimension_results[dim_key] = {
            "label": dim["label"],
            "description": dim["description"],
            "coverage": score["coverage"],
            "matching_sections": score["matching_sections"],
            "section_word_count": score["section_word_count"],
            "keyword_hits": score["keyword_hits"],
            "questions_to_ask": dim["questions"] if score["coverage"] != "good" else [],
        }

    good = [k for k, v in dimension_results.items() if v["coverage"] == "good"]
    thin = [k for k, v in dimension_results.items() if v["coverage"] == "thin"]
    missing = [k for k, v in dimension_results.items() if v["coverage"] == "missing"]

    score_map = {"good": 2, "thin": 1, "missing": 0}
    total = sum(score_map[v["coverage"]] for v in dimension_results.values())
    completeness_pct = round(total / (len(DIMENSIONS) * 2) * 100)

    if completeness_pct >= 75:
        overall = "comprehensive"
        interview_scope = "targeted"
    elif completeness_pct >= 40:
        overall = "partial"
        interview_scope = "focused"
    else:
        overall = "sparse"
        interview_scope = "full"

    questions_to_ask = []
    for dim_key in (thin + missing):
        for q in dimension_results[dim_key]["questions_to_ask"]:
            questions_to_ask.append({
                "dimension": dimension_results[dim_key]["label"],
                "question": q,
            })

    if interview_scope == "full":
        instructions = "Run the full specs interview — the spec is too sparse to skip much."
    elif not questions_to_ask:
        instructions = (
            f"Spec is {overall} ({completeness_pct}%). All dimensions covered. "
            "Skip the specs interview entirely; confirm key facts and move on."
        )
    else:
        well_covered = ", ".join(good) if good else "none"
        instructions = (
            f"Spec is {overall} ({completeness_pct}%). "
            f"Ask only the targeted questions in questions_to_ask. "
            f"Skip dimensions already well covered ({well_covered})."
        )

    return {
        "word_count": word_count,
        "line_count": line_count,
        "completeness_pct": completeness_pct,
        "overall": overall,
        "interview_scope": interview_scope,
        "dimensions": dimension_results,
        "summary": {"good": good, "thin": thin, "missing": missing},
        "questions_to_ask": questions_to_ask,
        "section_headers_found": [s["header"] for s in sections if s["header"] != "(intro)"],
        "claude_instructions": instructions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assess completeness of a SPECS.md file")
    parser.add_argument("spec_file", help="Path to the spec/PRD/requirements file")
    parser.add_argument("--output", default=None, help="Write JSON report to this path")
    args = parser.parse_args(argv)

    spec_path = Path(args.spec_file)
    if not spec_path.exists():
        print(f"❌ File not found: {args.spec_file}", file=sys.stderr)
        return 1

    content = spec_path.read_text(encoding="utf-8", errors="ignore")
    if not content.strip():
        print("❌ File is empty.", file=sys.stderr)
        return 1

    print(f"🔍 Assessing: {spec_path} ({len(content.split())} words)", file=sys.stderr)

    report = {"source_file": str(spec_path), **assess_spec(content)}

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f"✅ Report written to {args.output}", file=sys.stderr)
    else:
        print(json.dumps(report, indent=2))

    return {"comprehensive": 0, "partial": 1, "sparse": 2}[report["overall"]]


if __name__ == "__main__":
    sys.exit(main())
