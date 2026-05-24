"""sync — run build-registry, generate-action, and audit init in one shot.

Most teams want the same three steps after editing the doc-plan: rebuild
the registry, regenerate the GitHub Action, make sure the audit log
exists. `sync` is the shortcut so you don't have to memorize the order.

Usage:
    docs-gen sync .docs-meta/doc-plan.json
    docs-gen sync .docs-meta/doc-plan.json --output-dir . --strict
    docs-gen sync .docs-meta/doc-plan.json --skip-audit
"""

from __future__ import annotations

import argparse
from pathlib import Path

from docs_gen import log
from docs_gen.commands import build_registry as build_registry_cmd
from docs_gen.commands import generate_action as generate_action_cmd
from docs_gen.commands import audit as audit_cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs-gen sync",
        description="One-shot wrapper: build-registry → generate-action → audit init (if missing).",
    )
    parser.add_argument("doc_plan", help="Path to doc-plan.json")
    parser.add_argument("--output-dir", default=".",
                        help="Where to write the registry and DOCS_REGISTRY.md (default: .)")
    parser.add_argument("--workflows-dir", default=".github/workflows",
                        help="Where to write docs-check.yml (default: .github/workflows)")
    parser.add_argument("--audit-log", default="DOCS_AUDIT_LOG.md",
                        help="Path to the audit log file (default: DOCS_AUDIT_LOG.md)")
    parser.add_argument("--reviewer", default="[automated]",
                        help="Reviewer to record in the audit entry from sync (default: [automated])")
    parser.add_argument("--strict", action="store_true",
                        help="Pass --strict through to generate-action")
    parser.add_argument("--skip-audit", action="store_true",
                        help="Don't auto-init the audit log if missing, and don't append a sync entry")
    parser.add_argument("--dry-run", action="store_true",
                        help="Pass --dry-run through to every step")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    audit_log_path = Path(args.audit_log)

    # Step 1 — build registry, optionally appending an audit entry.
    log.info("→ build-registry")
    build_args = [args.doc_plan, str(output_dir)]
    if args.dry_run:
        build_args.append("--dry-run")
    if not args.skip_audit:
        build_args += ["--audit-log", str(audit_log_path), "--reviewer", args.reviewer]
    rc = build_registry_cmd.main(build_args)
    if rc != 0:
        log.error("build-registry failed; aborting sync.")
        return rc

    # Step 2 — generate the docs-check.yml workflow.
    log.info("→ generate-action")
    registry_path = output_dir / "docs-registry.yaml"
    gen_args = [str(registry_path), args.workflows_dir]
    if args.dry_run:
        gen_args.append("--dry-run")
    if args.strict:
        gen_args.append("--strict")
    if not args.skip_audit:
        gen_args += ["--audit-log", str(audit_log_path), "--reviewer", args.reviewer]
    rc = generate_action_cmd.main(gen_args)
    if rc != 0:
        log.error("generate-action failed; aborting sync.")
        return rc

    # Step 3 — ensure audit log exists.
    if args.skip_audit:
        log.info("Skipping audit log (--skip-audit).")
    elif audit_log_path.exists():
        log.info(f"Audit log already exists at {audit_log_path}; not re-initializing.")
    else:
        log.info("→ audit --init")
        init_args = ["--log", str(audit_log_path), "--init"]
        if args.dry_run:
            init_args.append("--dry-run")
        rc = audit_cmd.main(init_args)
        if rc != 0:
            log.error("audit --init failed; aborting sync.")
            return rc

    log.ok("sync complete.")
    return 0
