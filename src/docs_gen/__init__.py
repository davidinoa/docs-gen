"""docs-gen — generate, validate, and maintain a developer documentation ecosystem."""

from importlib.resources import files
from pathlib import Path

__version__ = "0.1.0"


def config_path(name: str) -> Path:
    """Locate a packaged config file by name.

    Examples:
        config_path("doc-types.yaml")
        config_path("claim-categories.yaml")

    Returns a path to the resource on disk. Works whether the package was
    installed normally or in editable mode.
    """
    return Path(str(files("docs_gen").joinpath(f"config/{name}")))


def template_path(name: str) -> Path:
    """Locate a packaged template file by name.

    Examples:
        template_path("doc-templates.md")
        template_path("adr-format.md")
    """
    return Path(str(files("docs_gen").joinpath(f"templates/{name}")))
