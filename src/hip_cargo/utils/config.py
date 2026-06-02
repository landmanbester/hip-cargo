"""Read container image from installed package metadata."""

import importlib
from pathlib import Path


def find_pyproject_toml(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: cwd) to find pyproject.toml.

    Args:
        start: Directory to start searching from (default: cwd).

    Returns:
        Path to pyproject.toml, or None if not found.
    """
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def get_container_image(package_name: str, package_import_name: str | None = None) -> str | None:
    """Return the container image registered in a package's _container_image module.

    Dynamically imports ``<package>._container_image`` and reads the
    ``CONTAINER_IMAGE`` constant. This works from any directory because it
    reads from the installed package, not from ``pyproject.toml``.

    Args:
        package_name:
            The distribution name of the package (e.g. 'pfb-imaging').
            By default hyphens are converted to underscores to determine the name of the module to to import.
        package_import_name:
            The name of the module to import (e.g. 'pfb_imaging').
            If not provided, it is derived from `package_name` by replacing hyphens with underscores.
    Returns:
        The full container image string (including tag), or None if the
        package is not installed or has no ``_container_image`` module.
    """
    if package_import_name is not None:
        pkg = package_import_name
    else:
        pkg = package_name.replace("-", "_")
    module_name = f"{pkg}._container_image"
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, "CONTAINER_IMAGE", None)
    except ModuleNotFoundError as exc:
        if exc.name and module_name.startswith(exc.name):
            # The package or its _container_image module is not installed
            return None
        raise
