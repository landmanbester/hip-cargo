"""Read container image from installed package metadata."""

import importlib


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
    try:
        mod = importlib.import_module(f"{pkg}._container_image")
        return getattr(mod, "CONTAINER_IMAGE", None)
    except ImportError:
        return None
