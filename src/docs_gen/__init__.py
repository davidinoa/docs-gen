"""docs-gen — generate, validate, and maintain a developer documentation ecosystem."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Iterable

__version__ = "0.3.0"

# Schema versions supported by this release. When we change a config or
# registry format incompatibly, bump the file's `version:` field AND add
# the new number to the set below. Older versions remain supported until
# explicitly dropped.
SUPPORTED_CONFIG_VERSIONS: set[int] = {1}
SUPPORTED_REGISTRY_VERSIONS: set[int] = {1}


class VersionMismatch(Exception):
    """Raised when a config or registry declares a version we don't support."""


def config_path(name: str) -> Path:
    """Locate a packaged config file by name.

    Examples:
        config_path("doc-types.yaml")
        config_path("claim-categories.yaml")
    """
    return Path(str(files("docs_gen").joinpath(f"config/{name}")))


def template_path(name: str) -> Path:
    """Locate a packaged template file by name.

    Examples:
        template_path("doc-templates.md")
        template_path("adr-format.md")
    """
    return Path(str(files("docs_gen").joinpath(f"templates/{name}")))


def check_version(value: object, supported: Iterable[int], *, what: str) -> int:
    """Validate a file's declared `version` field.

    Raises VersionMismatch if the value is missing, non-integer, or newer
    than what this release knows how to handle. Returns the integer version
    on success so callers can branch on it later if needed.
    """
    if value is None:
        raise VersionMismatch(
            f"{what} is missing a 'version' field. Expected one of {sorted(supported)}."
        )
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise VersionMismatch(
            f"{what} has non-integer version {value!r}. Expected one of {sorted(supported)}."
        )
    supported_set = set(supported)
    if n not in supported_set:
        raise VersionMismatch(
            f"{what} declares version {n}, which this release does not support "
            f"(supported: {sorted(supported_set)}). Update docs-gen or downgrade the file."
        )
    return n
