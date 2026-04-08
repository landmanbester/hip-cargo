"""Read container image from installed package metadata."""

import sys

if sys.version_info >= (3, 11):
    from importlib.metadata import distribution
else:
    from importlib_metadata import distribution


def get_container_image(package_name: str) -> str | None:
    """Return the container image registered in a package's entry points.

    Looks up the 'container-image' entry in the package's 'hip-cargo' entry
    point group. This reads from the installed package metadata via
    importlib.metadata, so it works from any directory — no CWD dependency.

    Args:
        package_name: The distribution name of the package (e.g. 'pfb-imaging').

    Returns:
        The full container image string (including tag), or None if not configured.

    Raises:
        PackageNotFoundError: If the package is not installed.
    """
    dist = distribution(package_name)
    for ep in dist.entry_points:
        if ep.group == "hip.cargo" and ep.name == "container-image":
            return ep.value
    return None
