"""Read project configuration from pyproject.toml."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


def find_pyproject_toml(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: cwd) to find pyproject.toml.

    Returns:
        Path to pyproject.toml, or None if not found.
    """
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def get_project_image(start: Path | None = None) -> str | None:
    """Read ``[tool.hip-cargo].image`` from the nearest pyproject.toml.

    This works for any project that stores its container image base
    under the ``[tool.hip-cargo]`` section in pyproject.toml.

    Args:
        start: Directory to start searching from (default: cwd).

    Returns:
        The image base string (without tag), or None if not configured.
    """
    pyproject = find_pyproject_toml(start)
    if pyproject is None:
        return None
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("hip-cargo", {}).get("image")
