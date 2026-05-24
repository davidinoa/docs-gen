#!/usr/bin/env python3
"""
append_audit.py — Append an entry to DOCS_AUDIT_LOG.md.

The audit log is append-only. This script adds one row.
Never edit existing entries — if something was wrong, add a new entry.

Usage:
    python append_audit.py \\
        --log <path/to/DOCS_AUDIT_LOG.md> \\
        --docs "ARCHITECTURE.md, STATE_MANAGEMENT.md" \\
        --change "Initial version created" \\
        --trigger "Project setup" \\
        --reviewer "[Name]"

    # Mark as reviewed with no changes:
    python append_audit.py \\
        --log DOCS_AUDIT_LOG.md \\
        --docs "RUNBOOK.md" \\
        --change "Reviewed, no changes needed" \\
        --trigger "PR #42" \\
        --reviewer "david"

    # Initialize a fresh log:
    python append_audit.py --log DOCS_AUDIT_LOG.md --init
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from docs_gen import log

HEADER = """\
# Docs Audit Log

Append-only log of every doc review, update, or conscious "no change needed" decision.
Never edit old entries — if something was wrong, add a new entry noting the correction.

---

| Date | Doc(s) | Change | Trigger | Reviewer |
|------|--------|--------|---------|----------|
"""


def init_log(log_path: Path, *, dry_run: bool = False) -> int:
    if log_path.exists():
        log.warn(f"{log_path} already exists. Use --append to add entries.")
        return 1
    if dry_run:
        log.info(f"[dry-run] would initialize audit log at: {log_path}")
        return 0
    log_path.write_text(HEADER)
    log.ok(f"Initialized: {log_path}")
    return 0


def append_entry(log_path: Path, docs: str, change: str, trigger: str, reviewer: str,
                 *, dry_run: bool = False) -> None:
    today = str(date.today())
    row = f"| {today} | {docs} | {change} | {trigger} | {reviewer} |\n"

    if dry_run:
        log.info(f"[dry-run] would append to {log_path}: {row.strip()}")
        return

    if not log_path.exists():
        log_path.write_text(HEADER)
        log.info(f"Created new log at {log_path}")

    content = log_path.read_text()

    # Ensure the table header exists; if not, append it
    if "| Date |" not in content:
        content = content.rstrip() + "\n\n" + "| Date | Doc(s) | Change | Trigger | Reviewer |\n"
        content += "|------|--------|--------|---------|----------|\n"

    log_path.write_text(content.rstrip() + "\n" + row)
    log.ok(f"Appended entry to {log_path}")
    log.debug(f"  Date:     {today}")
    log.debug(f"  Doc(s):   {docs}")
    log.debug(f"  Change:   {change}")
    log.debug(f"  Trigger:  {trigger}")
    log.debug(f"  Reviewer: {reviewer}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append an entry to DOCS_AUDIT_LOG.md")
    parser.add_argument("--log", default="DOCS_AUDIT_LOG.md", help="Path to audit log file")
    parser.add_argument("--init", action="store_true", help="Initialize a fresh audit log")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print intended write without modifying the filesystem")
    parser.add_argument("--docs", help="Doc filename(s) affected, comma-separated")
    parser.add_argument("--change", help="What changed (or 'Reviewed, no changes needed')")
    parser.add_argument("--trigger", help="What triggered this review (PR #N, sprint, manual, etc.)")
    parser.add_argument("--reviewer", default="[Name]", help="Who reviewed")
    args = parser.parse_args(argv)

    log_path = Path(args.log)

    if args.init:
        return init_log(log_path, dry_run=args.dry_run)

    missing = [f for f in ["docs", "change", "trigger"] if not getattr(args, f)]
    if missing:
        log.error(f"Missing required arguments: {', '.join('--' + m for m in missing)}")
        parser.print_help(file=sys.stderr)
        return 1

    append_entry(log_path, args.docs, args.change, args.trigger, args.reviewer,
                 dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
