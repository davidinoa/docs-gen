"""docs-gen — unified CLI entry point.

Dispatches to command modules in docs_gen.commands. Each subcommand parses
its own arguments and returns an exit code.

Installed as the `docs-gen` console script via pyproject.toml.
"""

from __future__ import annotations

import importlib
import sys
from typing import Callable

# Map subcommand → module name (under docs_gen.commands)
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
}


def _load_command(name: str) -> Callable[[list[str] | None], int]:
    """Lazy-import a command module's main() function."""
    module = importlib.import_module(f"docs_gen.commands.{name}")
    return module.main


def _print_help() -> None:
    from docs_gen import __version__
    print(f"docs-gen v{__version__}")
    print()
    print("Generate, validate, and maintain a developer documentation ecosystem.")
    print()
    print("Usage: docs-gen <subcommand> [args...]")
    print()
    print("Subcommands:")
    for cmd in COMMANDS:
        print(f"  {cmd}")
    print()
    print("Run `docs-gen <subcommand> --help` for subcommand-specific help.")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        _print_help()
        return 0 if argv else 1

    if argv[0] == "--version":
        from docs_gen import __version__
        print(f"docs-gen {__version__}")
        return 0

    subcommand = argv[0]
    if subcommand not in COMMANDS:
        print(f"❌ Unknown subcommand: {subcommand}", file=sys.stderr)
        print("   Run `docs-gen --help` for the list of subcommands.", file=sys.stderr)
        return 1

    module_name = COMMANDS[subcommand]
    cmd_main = _load_command(module_name)
    return cmd_main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
