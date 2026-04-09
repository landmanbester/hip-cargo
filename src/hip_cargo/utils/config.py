"""Read container image from installed package metadata."""

import importlib


def get_container_image(package_name: str) -> str | None:
    """Return the container image registered in a package's _container_image module.

    Dynamically imports ``<package>._container_image`` and reads the
    ``CONTAINER_IMAGE`` constant. This works from any directory because it
    reads from the installed package, not from ``pyproject.toml``.

    Args:
        package_name: The distribution name of the package (e.g. 'pfb-imaging').
            Hyphens are converted to underscores for the import.

    Returns:
        The full container image string (including tag), or None if the
        package is not installed or has no ``_container_image`` module.
    """
    pkg = package_name.replace("-", "_")
    try:
        mod = importlib.import_module(f"{pkg}._container_image")
        return getattr(mod, "CONTAINER_IMAGE", None)
    except (ImportError, ModuleNotFoundError):
        return None
