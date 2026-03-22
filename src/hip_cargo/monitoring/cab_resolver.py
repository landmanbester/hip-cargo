"""Resolve cab YAML files from _include entries and parse parameter schemas.

The cab YAML files are the canonical source of truth for command parameter
schemas. This module replaces the inspect-based discovery approach.
"""

import importlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hip_cargo.utils.config import find_pyproject_toml

_INCLUDE_RE = re.compile(r"\(([^)]+)\)(.+)")


def resolve_include(include_str: str) -> Path | None:
    """Resolve a stimela _include string to a file path.

    The format is (python.module)filename.yml where:
    - python.module is an importable Python package
    - filename.yml is a file within that package's directory

    Args:
        include_str: e.g. "(pfb_imaging.cabs)sara.yml"

    Returns:
        Path to the resolved YAML file, or None if the module
        cannot be imported or the file doesn't exist.
    """
    match = _INCLUDE_RE.match(include_str)
    if not match:
        return None

    module_path, filename = match.group(1), match.group(2)
    if not module_path:
        return None

    try:
        mod = importlib.import_module(module_path)
    except (ImportError, ModuleNotFoundError):
        return None

    if hasattr(mod, "__path__"):
        package_dir = Path(mod.__path__[0])
    elif hasattr(mod, "__file__") and mod.__file__:
        package_dir = Path(mod.__file__).parent
    else:
        return None

    resolved = package_dir / filename
    return resolved if resolved.is_file() else None


@dataclass
class CabParam:
    """A single parameter from a cab definition.

    Args:
        name: Parameter name (hyphenated as in YAML).
        dtype: Stimela type string.
        info: Help text.
        required: Whether the parameter is required.
        default: Default value.
        choices: Allowed values (if constrained).
        policies: Stimela policies dict.
        metadata: Additional metadata dict.
    """

    name: str
    dtype: str | None = None
    info: str = ""
    required: bool = False
    default: Any = None
    choices: list[Any] | None = None
    policies: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CabSchema:
    """Parsed parameter schema from a cab YAML file.

    Args:
        name: Cab name.
        info: Description.
        command: Python module path to the implementation.
        image: Container image URL (if any).
        inputs: Dict of input parameter schemas.
        outputs: Dict of output parameter schemas.
    """

    name: str
    info: str = ""
    command: str = ""
    image: str = ""
    inputs: dict[str, CabParam] = field(default_factory=dict)
    outputs: dict[str, CabParam] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON API responses."""
        return asdict(self)


def _parse_params(raw: dict[str, Any] | None) -> dict[str, CabParam]:
    """Parse a params block (inputs or outputs) into CabParam objects."""
    if not raw:
        return {}
    params = {}
    for name, defn in raw.items():
        if defn is None:
            defn = {}
        params[name] = CabParam(
            name=name,
            dtype=defn.get("dtype"),
            info=defn.get("info", ""),
            required=defn.get("required", False),
            default=defn.get("default"),
            choices=defn.get("choices"),
            policies=defn.get("policies") or {},
            metadata=defn.get("metadata") or {},
        )
    return params


def parse_cab_yaml(cab_path: str | Path) -> CabSchema:
    """Parse a cab YAML file and extract the parameter schema.

    Args:
        cab_path: Path to the cab YAML file.

    Returns:
        CabSchema with inputs and outputs populated.

    Raises:
        ValueError: If the YAML doesn't contain a valid cab definition.
    """
    cab_path = Path(cab_path)
    with open(cab_path) as f:
        parsed = yaml.safe_load(f)

    cabs = parsed.get("cabs")
    if not cabs or not isinstance(cabs, dict):
        raise ValueError(f"No 'cabs' block found in {cab_path}")

    # Take the first cab definition
    cab_name, cab_def = next(iter(cabs.items()))
    if cab_def is None:
        cab_def = {}

    return CabSchema(
        name=cab_def.get("name", cab_name),
        info=cab_def.get("info", ""),
        command=cab_def.get("command", ""),
        image=cab_def.get("image", ""),
        inputs=_parse_params(cab_def.get("inputs")),
        outputs=_parse_params(cab_def.get("outputs")),
    )


def resolve_recipe_cabs(includes: list[str]) -> dict[str, CabSchema]:
    """Resolve all _include entries from a recipe to cab schemas.

    Args:
        includes: List of _include strings from the recipe YAML.

    Returns:
        Dict mapping cab name to CabSchema. Cabs whose packages
        are not installed are silently skipped.
    """
    result = {}
    for include_str in includes:
        path = resolve_include(include_str)
        if path is None:
            continue
        try:
            schema = parse_cab_yaml(path)
            result[schema.name] = schema
        except (ValueError, yaml.YAMLError):
            continue
    return result


def discover_project_cabs(cli_module_path: str | None = None) -> list[dict]:
    """Discover cabs from the current project.

    Tries:
    1. If cli_module_path is provided, find sibling 'cabs' package
       (e.g. "pfb.cli" -> "pfb.cabs")
    2. Read [tool.hip-cargo] from pyproject.toml for package info
    3. Return empty list if nothing found

    Args:
        cli_module_path: Dotted module path (e.g. "pfb.cli").

    Returns:
        List of cab schema dicts.
    """
    cabs_dir = _find_cabs_dir(cli_module_path)
    if cabs_dir is None or not cabs_dir.is_dir():
        return []

    results = []
    for yml_path in sorted(cabs_dir.glob("*.yml")):
        try:
            schema = parse_cab_yaml(yml_path)
            results.append(schema.to_dict())
        except (ValueError, yaml.YAMLError):
            continue
    return results


def _find_cabs_dir(cli_module_path: str | None) -> Path | None:
    """Locate the cabs directory for a project."""
    # Try sibling cabs package from CLI module path
    if cli_module_path:
        parts = cli_module_path.rsplit(".", 1)
        if len(parts) == 2:
            cabs_module = f"{parts[0]}.cabs"
        else:
            cabs_module = f"{parts[0]}.cabs"
        try:
            mod = importlib.import_module(cabs_module)
            if hasattr(mod, "__path__"):
                return Path(mod.__path__[0])
        except (ImportError, ModuleNotFoundError):
            pass

    # Try pyproject.toml to infer package name
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

    # Try the project's own package
    project_name = data.get("project", {}).get("name", "")
    if project_name:
        package_name = project_name.replace("-", "_")
        cabs_module = f"{package_name}.cabs"
        try:
            mod = importlib.import_module(cabs_module)
            if hasattr(mod, "__path__"):
                return Path(mod.__path__[0])
        except (ImportError, ModuleNotFoundError):
            pass

    return None
