#!/usr/bin/env python3
"""
state.py — Track progress through the docs generation workflow.

Maintains .docs-meta/state.json in the target repo. Lets Claude (and humans)
see where the workflow is, what's been done, and which artifacts exist.
Enables idempotency: re-running the skill on the same repo picks up from
the last completed step rather than starting over.

Usage:
    python state.py init <repo_path>
    python state.py status [--repo .]
    python state.py advance --repo . --step <name> [--artifact key=path] ...
    python state.py get --repo . --field <field_name>
    python state.py reset --repo .
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Canonical pipeline step order. The skill follows this order.
PIPELINE_STEPS = [
    "specs",       # SPECS.md created/adopted
    "interview",   # project-context.json written
    "scan",        # scan-results.json written
    "plan",        # doc-plan.json written
    "generate",    # all doc files written
    "validate",    # validation-report.json written and resolved
    "registry",    # docs-registry.yaml + DOCS_REGISTRY.md written
    "action",      # .github/workflows/docs-check.yml written
    "audit",       # DOCS_AUDIT_LOG.md initialized + initial entries
    "complete",    # workflow done
]


def state_dir(repo: Path) -> Path:
    return repo / ".docs-meta"


def state_path(repo: Path) -> Path:
    return state_dir(repo) / "state.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_state(repo: Path) -> dict:
    sd = state_dir(repo)
    sd.mkdir(parents=True, exist_ok=True)

    state = {
        "version": 1,
        "started_at": now_iso(),
        "last_updated": now_iso(),
        "repo_path": str(repo.resolve()),
        "current_step": "specs",
        "completed_steps": [],
        "pipeline_steps": PIPELINE_STEPS,
        "artifacts": {},
        "outputs_written": [],
    }
    state_path(repo).write_text(json.dumps(state, indent=2))
    return state


def load_state(repo: Path) -> dict:
    sp = state_path(repo)
    if not sp.exists():
        print(f"❌ No state file at {sp}. Run `state.py init` first.", file=sys.stderr)
        sys.exit(1)
    return json.loads(sp.read_text())


def save_state(repo: Path, state: dict) -> None:
    state["last_updated"] = now_iso()
    state_path(repo).write_text(json.dumps(state, indent=2))


def advance(repo: Path, step: str, artifacts: dict, outputs: list[str], force: bool = False) -> dict:
    if step not in PIPELINE_STEPS:
        print(f"❌ Unknown step: {step}. Valid: {', '.join(PIPELINE_STEPS)}", file=sys.stderr)
        sys.exit(1)

    state = load_state(repo)

    # Order check: warn if completing a step that's after the current expected step
    current = state["current_step"]
    if step != current and step not in state["completed_steps"]:
        step_idx = PIPELINE_STEPS.index(step)
        current_idx = PIPELINE_STEPS.index(current) if current in PIPELINE_STEPS else -1
        if step_idx > current_idx:
            skipped = PIPELINE_STEPS[current_idx:step_idx]
            if not force:
                print(f"⚠️  Skipping ahead from '{current}' to '{step}'. Missed: {', '.join(skipped)}", file=sys.stderr)
                print(f"   Re-run with --force if intentional, or run the missed steps first.", file=sys.stderr)
                sys.exit(2)
            else:
                print(f"⚠️  Skipping ahead (forced). Missed steps: {', '.join(skipped)}", file=sys.stderr)

    if step in state["completed_steps"]:
        print(f"ℹ️  Step '{step}' was already complete. Updating artifacts only.", file=sys.stderr)
    else:
        state["completed_steps"].append(step)

    # Move current_step forward to the next incomplete step in pipeline order
    completed = set(state["completed_steps"])
    next_step = None
    for s in PIPELINE_STEPS:
        if s not in completed:
            next_step = s
            break
    state["current_step"] = next_step or "complete"

    state["artifacts"].update(artifacts)
    for o in outputs:
        if o not in state["outputs_written"]:
            state["outputs_written"].append(o)

    save_state(repo, state)
    return state


def print_status(state: dict) -> None:
    print(f"📍 Repo:           {state['repo_path']}")
    print(f"📅 Started:        {state['started_at']}")
    print(f"📅 Last updated:   {state['last_updated']}")
    print(f"➡️  Current step:   {state['current_step']}")
    print(f"✅ Completed:      {len(state['completed_steps'])} / {len(state['pipeline_steps'])}")
    print()
    print("Pipeline:")
    completed = set(state["completed_steps"])
    for s in state["pipeline_steps"]:
        if s in completed:
            marker = "✅"
        elif s == state["current_step"]:
            marker = "➡️ "
        else:
            marker = "  "
        print(f"  {marker} {s}")
    print()
    if state["artifacts"]:
        print("Artifacts:")
        for k, v in state["artifacts"].items():
            print(f"  {k:20} → {v}")
    print()
    if state["outputs_written"]:
        print("Outputs written:")
        for o in state["outputs_written"]:
            print(f"  • {o}")


def parse_artifact_args(args: list[str]) -> dict:
    """Parse 'key=path' style artifact args."""
    result = {}
    for a in args:
        if "=" not in a:
            print(f"⚠️  Skipping malformed artifact arg: {a} (expected key=path)", file=sys.stderr)
            continue
        k, v = a.split("=", 1)
        result[k.strip()] = v.strip()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Track docs-generator workflow state")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize state in a repo")
    p_init.add_argument("repo_path")

    p_status = sub.add_parser("status", help="Show current state")
    p_status.add_argument("--repo", default=".")
    p_status.add_argument("--json", action="store_true", help="Output raw JSON state")

    p_advance = sub.add_parser("advance", help="Mark a step complete")
    p_advance.add_argument("--repo", default=".")
    p_advance.add_argument("--step", required=True, choices=PIPELINE_STEPS)
    p_advance.add_argument("--artifact", action="append", default=[], help="key=path (repeatable)")
    p_advance.add_argument("--output", action="append", default=[], help="Output file path (repeatable)")
    p_advance.add_argument("--force", action="store_true", help="Skip the order check")

    p_get = sub.add_parser("get", help="Read a single field")
    p_get.add_argument("--repo", default=".")
    p_get.add_argument("--field", required=True)

    p_reset = sub.add_parser("reset", help="Delete state and start over")
    p_reset.add_argument("--repo", default=".")
    p_reset.add_argument("--yes", action="store_true", help="Skip confirmation")

    args = parser.parse_args(argv)

    if args.cmd == "init":
        repo = Path(args.repo_path)
        if state_path(repo).exists():
            print(f"⚠️  State already exists at {state_path(repo)}", file=sys.stderr)
            print(f"   Use `state.py reset` to start over, or `state.py status` to see current state.", file=sys.stderr)
            return 1
        state = init_state(repo)
        print(f"✅ Initialized state at {state_path(repo)}", file=sys.stderr)
        print(json.dumps(state, indent=2))
        return

    if args.cmd == "status":
        repo = Path(args.repo)
        state = load_state(repo)
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print_status(state)
        return

    if args.cmd == "advance":
        repo = Path(args.repo)
        artifacts = parse_artifact_args(args.artifact)
        state = advance(repo, args.step, artifacts, args.output, force=args.force)
        print(f"✅ Advanced to step '{state['current_step']}' (completed: {args.step})", file=sys.stderr)
        return

    if args.cmd == "get":
        repo = Path(args.repo)
        state = load_state(repo)
        if args.field not in state:
            print(f"❌ No field '{args.field}'. Available: {', '.join(state.keys())}", file=sys.stderr)
            return 1
        val = state[args.field]
        if isinstance(val, (dict, list)):
            print(json.dumps(val, indent=2))
        else:
            print(val)
        return

    if args.cmd == "reset":
        repo = Path(args.repo)
        sp = state_path(repo)
        if not sp.exists():
            print(f"ℹ️  No state to reset at {sp}", file=sys.stderr)
            return
        if not args.yes:
            print(f"⚠️  This will delete {sp}. Re-run with --yes to confirm.", file=sys.stderr)
            return 1
        sp.unlink()
        print(f"✅ Deleted {sp}", file=sys.stderr)
        return


if __name__ == "__main__":
    sys.exit(main())
