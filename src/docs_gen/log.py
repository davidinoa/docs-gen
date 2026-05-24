"""Status logging for docs-gen subcommands.

Centralizes stderr output so the CLI can control verbosity and format.
All commands should emit status through these helpers rather than calling
print(..., file=sys.stderr) directly — that way --verbose/--quiet and
--log-format=json work uniformly.

Configured by docs_gen.cli before subcommand dispatch.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

# Verbosity levels: 0 = quiet (errors only), 1 = normal, 2 = verbose
_VERBOSITY = 1
_FORMAT = "text"

# Env vars used to propagate configuration to subprocesses (the test suite
# invokes docs-gen via subprocess, so per-call state isn't enough).
ENV_VERBOSITY = "DOCS_GEN_VERBOSITY"
ENV_FORMAT = "DOCS_GEN_LOG_FORMAT"


def _init_from_env() -> None:
    global _VERBOSITY, _FORMAT
    try:
        _VERBOSITY = int(os.environ.get(ENV_VERBOSITY, "1"))
    except ValueError:
        _VERBOSITY = 1
    fmt = os.environ.get(ENV_FORMAT, "text").lower()
    _FORMAT = "json" if fmt == "json" else "text"


def configure(verbose: bool = False, quiet: bool = False, log_format: str = "text") -> None:
    """Set verbosity and output format. Called from cli.py."""
    global _VERBOSITY, _FORMAT
    if quiet:
        _VERBOSITY = 0
    elif verbose:
        _VERBOSITY = 2
    else:
        _VERBOSITY = 1
    _FORMAT = "json" if log_format.lower() == "json" else "text"
    os.environ[ENV_VERBOSITY] = str(_VERBOSITY)
    os.environ[ENV_FORMAT] = _FORMAT


def is_json() -> bool:
    return _FORMAT == "json"


def _emit(level: str, message: str, **extra: Any) -> None:
    if _FORMAT == "json":
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        if extra:
            payload.update(extra)
        print(json.dumps(payload), file=sys.stderr)
    else:
        prefix_map = {
            "debug": "🔬",
            "info":  "ℹ️ ",
            "ok":    "✅",
            "warn":  "⚠️ ",
            "error": "❌",
        }
        prefix = prefix_map.get(level, "")
        if prefix:
            print(f"{prefix} {message}", file=sys.stderr)
        else:
            print(message, file=sys.stderr)


def debug(message: str, **extra: Any) -> None:
    if _VERBOSITY >= 2:
        _emit("debug", message, **extra)


def info(message: str, **extra: Any) -> None:
    if _VERBOSITY >= 1:
        _emit("info", message, **extra)


def ok(message: str, **extra: Any) -> None:
    if _VERBOSITY >= 1:
        _emit("ok", message, **extra)


def warn(message: str, **extra: Any) -> None:
    if _VERBOSITY >= 1:
        _emit("warn", message, **extra)


def error(message: str, **extra: Any) -> None:
    # Errors are always emitted, even under --quiet.
    _emit("error", message, **extra)


_init_from_env()
