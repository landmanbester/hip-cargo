"""Discover stimela recipe YAML files in a project."""

from pathlib import Path

from hip_cargo.utils.config import find_pyproject_toml


def _get_recipes_dir_from_pyproject() -> Path | None:
    """Read [tool.hip-cargo].recipes_dir from pyproject.toml."""
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
    recipes_dir = data.get("tool", {}).get("hip-cargo", {}).get("recipes_dir")
    if recipes_dir is not None:
        return pyproject.parent / recipes_dir
    return None


def discover_recipes(recipes_dir: str | Path | None = None) -> list[dict]:
    """Find recipe YAML files in the project.

    Looks in:
    1. recipes_dir if provided
    2. [tool.hip-cargo].recipes_dir from pyproject.toml
    3. ./recipes/ relative to cwd
    4. Returns empty list if nothing found

    Args:
        recipes_dir: Explicit directory to search.

    Returns:
        List of {"name": str, "path": str} dicts.
    """
    search_dir: Path | None = None
    if recipes_dir is not None:
        search_dir = Path(recipes_dir)
    else:
        search_dir = _get_recipes_dir_from_pyproject()
        if search_dir is None:
            candidate = Path.cwd() / "recipes"
            if candidate.is_dir():
                search_dir = candidate

    if search_dir is None or not search_dir.is_dir():
        return []

    return [{"name": p.stem, "path": str(p)} for p in sorted(search_dir.glob("*.yml"))]


def find_recipe(name: str, recipes_dir: str | Path | None = None) -> Path:
    """Find a recipe by name.

    Args:
        name: Recipe name (stem of the YAML file, without .yml).
        recipes_dir: Explicit directory to search.

    Returns:
        Path to the recipe file.

    Raises:
        FileNotFoundError: If the recipe is not found.
    """
    recipes = discover_recipes(recipes_dir)
    for r in recipes:
        if r["name"] == name:
            return Path(r["path"])
    raise FileNotFoundError(f"Recipe '{name}' not found")
