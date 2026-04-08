"""Read container image from installed package metadata."""

import sys

if sys.version_info >= (3, 11):
    from importlib.metadata import metadata
else:
    from importlib_metadata import metadata


def get_container_image(package_name: str) -> str | None:
    """Return the container image URL registered in a package's project metadata.

    Looks up the 'Container' entry under [project.urls] in the package metadata.
    This reads from the installed package metadata via importlib.metadata, so it
    works from any directory — no CWD dependency.

    Args:
        package_name: The distribution name of the package (e.g. 'pfb-imaging').

    Returns:
        The full container image string (including tag), or None if not configured.

    Raises:
        PackageNotFoundError: If the package is not installed.
    """
    meta = metadata(package_name)
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() == "container":
            return url.strip()
    return None
