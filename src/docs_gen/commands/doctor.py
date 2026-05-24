#!/usr/bin/env python3
"""
doctor.py — Check the health of an existing docs ecosystem.

Verifies that:
  - The registry exists and references files that actually exist
  - All registered docs are present in the repo
  - Any docs in the repo that aren't registered (unmapped territory)
  - Registry path mappings still match real directories
  - Audit log and GitHub Action are present
  - The state file (if any) is consistent with reality

Run periodically (e.g., as part of CI) or whenever the docs ecosystem feels stale.

Usage:
    python doctor.py <repo_path>
    python doctor.py . --output health-report.json

Exit codes:
    0 — healthy
    1 — issues found (review recommended)
    2 — critical issues (registry missing or broken)
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


def find_md_files(repo: Path) -> set[str]:
    """Find all markdown files in the repo (excluding common ignores)."""
    ignore_dirs = {"node_modules", ".git", "dist", "build", ".next", "venv", ".venv"}
    found = set()
    for path in repo.rglob("*.md"):
        # Skip if any path part is in ignore_dirs
        if any(part in ignore_dirs for part in path.relative_to(repo).parts):
            continue
        found.add(str(path.relative_to(repo)))
    return found


def path_glob_exists(repo: Path, pattern: str) -> bool:
    """Check if at least one path matches the glob pattern in the repo."""
    # Convert "src/**" → glob-pattern-compatible
    # Simple check: just try to match
    if "*" not in pattern:
        return (repo / pattern).exists()
    try:
        return any(repo.glob(pattern))
    except Exception:
        return False


def check_ecosystem(repo: Path) -> dict:
    """Run all health checks. Returns structured report."""
    report = {
        "repo_path": str(repo),
        "summary": {"critical": 0, "issues": 0, "info": 0, "ok": 0},
        "checks": [],
    }

    def add(level: str, name: str, status: str, detail: str = ""):
        report["checks"].append({"level": level, "name": name, "status": status, "detail": detail})
        if status == "fail":
            if level == "critical":
                report["summary"]["critical"] += 1
            else:
                report["summary"]["issues"] += 1
        elif status == "warn":
            report["summary"]["info"] += 1
        else:
            report["summary"]["ok"] += 1

    # ── Health system files ──
    registry_yaml = repo / "docs-registry.yaml"
    registry_md = repo / "DOCS_REGISTRY.md"
    audit_log = repo / "DOCS_AUDIT_LOG.md"
    action_file = repo / ".github" / "workflows" / "docs-check.yml"
    state_file = repo / ".docs-meta" / "state.json"

    if not registry_yaml.exists():
        add("critical", "registry_yaml_exists", "fail",
            f"{registry_yaml} not found. The registry is the source of truth — without it, "
            "the ecosystem can't be checked.")
        return report  # No point continuing without a registry

    add("info", "registry_yaml_exists", "pass")

    if not registry_md.exists():
        add("issue", "registry_md_exists", "fail",
            "DOCS_REGISTRY.md not found. Regenerate with: build_registry.py")
    else:
        add("info", "registry_md_exists", "pass")

    if not audit_log.exists():
        add("issue", "audit_log_exists", "fail",
            "DOCS_AUDIT_LOG.md not found. Initialize with: append_audit.py --init")
    else:
        add("info", "audit_log_exists", "pass")

    if not action_file.exists():
        add("issue", "action_exists", "fail",
            f"{action_file} not found. Regenerate with: generate_action.py")
    else:
        add("info", "action_exists", "pass")

    # ── Registry contents ──
    try:
        registry = yaml.safe_load(registry_yaml.read_text())
    except Exception as e:
        add("critical", "registry_yaml_parses", "fail", f"Cannot parse registry: {e}")
        return report

    add("info", "registry_yaml_parses", "pass")

    registered_docs = {d["file"] for d in registry.get("docs", [])}

    # ── Missing files: registered but not in repo ──
    missing_files = []
    for d in registry.get("docs", []):
        filename = d["file"]
        if not (repo / filename).exists():
            # Could be in a subdir — try a recursive search
            matches = list(repo.rglob(filename))
            matches = [m for m in matches if ".git" not in m.parts and "node_modules" not in m.parts]
            if not matches:
                missing_files.append(filename)

    if missing_files:
        add("issue", "registered_docs_exist", "fail",
            f"Files in registry but not in repo: {', '.join(missing_files)}. "
            "Either restore them or remove from docs-registry.yaml.")
    else:
        add("info", "registered_docs_exist", "pass")

    # ── Unregistered docs: in repo but not in registry ──
    all_md = find_md_files(repo)
    skip = {"DOCS_REGISTRY.md", "DOCS_AUDIT_LOG.md", "LICENSE.md"}
    unregistered = []
    for md in all_md:
        name = Path(md).name
        if name in skip:
            continue
        if name not in registered_docs and md not in registered_docs:
            unregistered.append(md)

    if unregistered:
        add("issue", "all_docs_registered", "fail",
            f"Markdown files not in registry: {', '.join(sorted(unregistered))}. "
            "Either enroll them in docs-registry.yaml or move them out of the docs tree.")
    else:
        add("info", "all_docs_registered", "pass")

    # ── Stale paths: registry references paths that no longer exist ──
    stale_paths = []
    for d in registry.get("docs", []):
        for p in d.get("paths", []):
            if not path_glob_exists(repo, p):
                stale_paths.append((d["file"], p))

    if stale_paths:
        details = "; ".join(f"{doc} → `{p}`" for doc, p in stale_paths)
        add("issue", "registry_paths_exist", "fail",
            f"Registry references {len(stale_paths)} path(s) that don't exist: {details}. "
            "Either update the paths in docs-registry.yaml or fix the repo structure.")
    else:
        add("info", "registry_paths_exist", "pass")

    # ── State file consistency ──
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            if state.get("current_step") != "complete":
                add("issue", "state_complete", "fail",
                    f"State file shows incomplete workflow (current step: {state.get('current_step')}). "
                    f"Resume with: state.py status --repo {repo}")
            else:
                add("info", "state_complete", "pass")
        except Exception as e:
            add("issue", "state_file_parses", "fail", f"Cannot parse state file: {e}")
    else:
        add("info", "state_file_present", "pass", "(optional, not required)")

    # ── GitHub Action consistency with registry ──
    if action_file.exists():
        action_text = action_file.read_text()
        # Quick check: each non-custom doc with paths should appear in the action
        docs_with_paths = [d for d in registry.get("docs", []) if d.get("paths")]
        missing_from_action = []
        for d in docs_with_paths:
            if d["file"] not in action_text:
                missing_from_action.append(d["file"])
        if missing_from_action:
            add("issue", "action_matches_registry", "fail",
                f"Registry has path mappings for {missing_from_action}, but they don't appear in "
                f"the GitHub Action. Regenerate with: generate_action.py")
        else:
            add("info", "action_matches_registry", "pass")

    return report


def print_report(report: dict) -> None:
    summary = report["summary"]
    print(f"\n📋 Docs Ecosystem Health — {report['repo_path']}\n")

    ok = summary["ok"]
    info = summary["info"]
    issues = summary["issues"]
    critical = summary["critical"]

    for check in report["checks"]:
        if check["status"] == "pass":
            marker = "✅"
        elif check["level"] == "critical":
            marker = "🔴"
        else:
            marker = "🟡"
        line = f"  {marker} {check['name']}"
        if check["detail"]:
            line += f"\n     → {check['detail']}"
        print(line)

    print()
    if critical:
        print(f"🔴 {critical} critical issue(s) — the ecosystem can't be fully checked.")
    elif issues:
        print(f"🟡 {issues} issue(s) found — review recommended.")
    else:
        print(f"✅ All checks passed.")


def run_content_validation(repo: Path) -> dict:
    """Run content validation on all .md files in the repo. Returns issue counts and details."""
    md_files = sorted(find_md_files(repo))
    md_paths = [repo / m for m in md_files if Path(m).name not in
                {"DOCS_REGISTRY.md", "DOCS_AUDIT_LOG.md", "LICENSE.md"}]
    if not md_paths:
        return {"ran": False, "reason": "No docs to validate"}

    # Import the validate_docs module directly — no subprocess needed
    try:
        from docs_gen.commands import validate_docs as vd
    except ImportError as e:
        return {"ran": False, "reason": f"Could not import validate_docs: {e}"}

    docs: dict[str, str] = {}
    for p in md_paths:
        if p.exists():
            docs[p.name] = p.read_text(encoding="utf-8", errors="ignore")

    if not docs:
        return {"ran": False, "reason": "No readable docs"}

    try:
        categories = vd.load_claim_categories()
    except Exception as e:
        return {"ran": False, "reason": f"Could not load claim categories: {e}"}

    issues = []
    issues.extend(vd.check_duplicate_headers(docs))
    issues.extend(vd.check_env_var_conflicts(docs))
    issues.extend(vd.check_version_conflicts(docs))
    claim_issues, _ = vd.check_claim_conflicts(docs, categories)
    issues.extend(claim_issues)

    summary = {
        "high": sum(1 for i in issues if i["severity"] == "high"),
        "medium": sum(1 for i in issues if i["severity"] == "medium"),
        "low": sum(1 for i in issues if i["severity"] == "low"),
    }

    return {
        "ran": True,
        "summary": summary,
        "issues": [
            {"type": i["type"], "severity": i["severity"], "message": i["message"]}
            for i in issues
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check docs ecosystem health")
    parser.add_argument("repo_path", nargs="?", default=".")
    parser.add_argument("--output", default=None, help="Write JSON report to this path")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of formatted")
    parser.add_argument("--full", action="store_true",
                        help="Also run content validation (contradictions, claim conflicts)")
    args = parser.parse_args(argv)

    repo = Path(args.repo_path).resolve()
    if not repo.exists():
        print(f"❌ Repo not found: {repo}", file=sys.stderr)
        return 2

    print(f"🩺 Examining {repo}", file=sys.stderr)
    report = check_ecosystem(repo)

    # Optional content validation pass
    if args.full:
        print("🔬 Running content validation (--full)", file=sys.stderr)
        content = run_content_validation(repo)
        report["content_validation"] = content
        if content.get("ran") and content.get("summary"):
            cs = content["summary"]
            # Roll content issues into the overall summary so exit codes reflect them
            report["summary"]["issues"] += cs.get("high", 0) + cs.get("medium", 0)

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f"✅ Report written to {args.output}", file=sys.stderr)
    elif args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
        if args.full and "content_validation" in report and report["content_validation"].get("ran"):
            cv = report["content_validation"]
            print()
            print(f"🔬 Content validation: {cv['summary']}")
            for i in cv["issues"]:
                marker = "🔴" if i["severity"] == "high" else "🟡" if i["severity"] == "medium" else "  "
                print(f"  {marker} [{i['type']}] {i['message'][:120]}")

    summary = report["summary"]
    if summary["critical"]:
        return 2
    elif summary["issues"]:
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
