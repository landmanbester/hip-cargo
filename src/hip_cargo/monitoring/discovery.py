"""Auto-discover CLI commands from the current project's Typer app."""

import importlib
import inspect
from typing import Any

from hip_cargo.utils.config import find_pyproject_toml


def _get_cli_module_from_pyproject() -> str | None:
    """Read [tool.hip-cargo].cli_module from pyproject.toml."""
    pyproject = find_pyproject_toml()
    if pyproject is None:
        return None
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomllib  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("hip-cargo", {}).get("cli_module")


def _extract_param_info(param: inspect.Parameter) -> dict[str, Any]:
    """Extract basic parameter info from an inspect.Parameter."""
    info: dict[str, Any] = {"name": param.name}
    if param.annotation != inspect.Parameter.empty:
        info["type"] = str(param.annotation)
    if param.default != inspect.Parameter.empty:
        info["default"] = param.default
        info["required"] = False
    else:
        info["required"] = True
    return info


def discover_commands(cli_module_path: str | None = None) -> list[dict]:
    """Discover available CLI commands and their parameter schemas.

    Attempts to find the CLI module by:
    1. Using cli_module_path if provided
    2. Reading [tool.hip-cargo].cli_module from pyproject.toml
    3. Returning empty list if neither is available

    Args:
        cli_module_path: Dotted module path to import (e.g. "pfb.cli").

    Returns:
        List of dicts with name, description, and parameters for each command.
    """
    module_path = cli_module_path or _get_cli_module_from_pyproject()
    if module_path is None:
        return []

    try:
        mod = importlib.import_module(module_path)
    except (ImportError, ModuleNotFoundError):
        return []

    # Look for a Typer app instance
    typer_app = getattr(mod, "app", None)
    if typer_app is None:
        return []

    commands = []
    for cmd_info in getattr(typer_app, "registered_commands", []):
        callback = cmd_info.callback
        if callback is None:
            continue

        name = cmd_info.name or getattr(callback, "__name__", "unknown")
        description = getattr(callback, "__doc__", "") or ""

        # Try stimela metadata first, fall back to basic inspection
        cab_config = getattr(callback, "__stimela_cab_config__", None)
        if cab_config:
            description = cab_config.get("info", description)

        sig = inspect.signature(callback)
        parameters = [_extract_param_info(p) for p in sig.parameters.values()]

        commands.append(
            {
                "name": name,
                "description": description.strip(),
                "parameters": parameters,
            }
        )

    return commands
