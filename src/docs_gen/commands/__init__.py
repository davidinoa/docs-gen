"""Command modules for the docs-gen CLI.

Each module exposes a `main(argv: list[str] | None = None) -> int` function
that parses its own arguments and returns an exit code. The unified CLI in
`docs_gen.cli` dispatches to these.

These modules can also be imported and used programmatically.
"""
