"""docs-gen — unified CLI entry point.

Dispatches to command modules in docs_gen.commands. Each subcommand parses
its own arguments and returns an exit code. Global flags (--verbose,
--quiet, --log-format) are stripped from argv before dispatch and used
to configure docs_gen.log.

Installed as the `docs-gen` console script via pyproject.toml.
"""

from __future__ import annotations

import importlib
import sys
from typing import Callable

from docs_gen import log

COMMANDS: dict[str, str] = {
    "scan":            "scan",
    "assess":          "assess",
    "validate-plan":   "validate_plan",
    "build-registry":  "build_registry",
    "generate-action": "generate_action",
    "validate":        "validate_docs",
    "audit":           "audit",
    "doctor":          "doctor",
    "state":           "state",
    "template":        "template",
    "codeowners":      "codeowners",
    "snapshot":        "snapshot",
    "lookup":          "lookup",
    "sync":            "sync",
    "init":            "init",
}


def _load_command(name: str) -> Callable[[list[str] | None], int]:
    module = importlib.import_module(f"docs_gen.commands.{name}")
    return module.main


def _print_help() -> None:
    from docs_gen import __version__
    print(f"docs-gen v{__version__}")
    print()
    print("Generate, validate, and maintain a developer documentation ecosystem.")
    print()
    print("Usage: docs-gen [--verbose | --quiet] [--log-format text|json] <subcommand> [args...]")
    print()
    print("Global flags:")
    print("  --verbose          More detailed status output")
    print("  --quiet            Suppress status output (errors still printed)")
    print("  --log-format FMT   text (default) or json — structured status events")
    print("  --version          Print version and exit")
    print()
    print("Subcommands:")
    for cmd in COMMANDS:
        print(f"  {cmd}")
    print()
    print("Run `docs-gen <subcommand> --help` for subcommand-specific help.")


def _extract_global_flags(argv: list[str]) -> tuple[dict, list[str]]:
    """Strip global flags from argv and return (config, remaining).

    Subcommand args remain untouched. Anything after a subcommand name is
    passed through verbatim — including their own --verbose/--quiet which
    are not supported per-subcommand.
    """
    config = {"verbose": False, "quiet": False, "log_format": "text"}
    remaining: list[str] = []
    i = 0
    subcommand_seen = False
    while i < len(argv):
        token = argv[i]
        if not subcommand_seen:
            if token in ("--verbose", "-v"):
                config["verbose"] = True
                i += 1
                continue
            if token in ("--quiet", "-q"):
                config["quiet"] = True
                i += 1
                continue
            if token == "--log-format":
                if i + 1 < len(argv):
                    config["log_format"] = argv[i + 1]
                    i += 2
                    continue
                i += 1
                continue
            if token.startswith("--log-format="):
                config["log_format"] = token.split("=", 1)[1]
                i += 1
                continue
            # First positional token (not a global flag) → subcommand.
            if not token.startswith("-"):
                subcommand_seen = True
        remaining.append(token)
        i += 1
    return config, remaining


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    config, argv = _extract_global_flags(argv)
    log.configure(
        verbose=config["verbose"],
        quiet=config["quiet"],
        log_format=config["log_format"],
    )

    if not argv or argv[0] in ("-h", "--help", "help"):
        _print_help()
        return 0 if argv else 1

    if argv[0] == "--version":
        from docs_gen import __version__
        print(f"docs-gen {__version__}")
        return 0

    subcommand = argv[0]
    if subcommand not in COMMANDS:
        log.error(f"Unknown subcommand: {subcommand}")
        log.error("Run `docs-gen --help` for the list of subcommands.")
        return 1

    cmd_main = _load_command(COMMANDS[subcommand])
    return cmd_main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
