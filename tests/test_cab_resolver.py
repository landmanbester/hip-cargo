"""Tests for cab-based schema resolution."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from hip_cargo.monitoring.cab_resolver import (
    discover_project_cabs,
    parse_cab_yaml,
    resolve_include,
    resolve_recipe_cabs,
)
from hip_cargo.monitoring.recipe_parser import parse_recipe

FIXTURES = Path(__file__).parent / "fixtures"


# --- resolve_include ---


def test_resolve_include_hip_cargo_cabs():
    """Resolves hip-cargo's own cab YAML file."""
    path = resolve_include("(hip_cargo.cabs)generate_cabs.yml")
    assert path is not None
    assert path.exists()
    assert path.name == "generate_cabs.yml"


def test_resolve_include_missing_module():
    """Returns None for an uninstalled package."""
    assert resolve_include("(nonexistent.package)foo.yml") is None


def test_resolve_include_missing_file():
    """Returns None when module exists but file doesn't."""
    assert resolve_include("(hip_cargo.cabs)nonexistent.yml") is None


def test_resolve_include_valid_deep_module():
    """Parses (a.b.c)file.yml format correctly."""
    # hip_cargo.cabs exists, but deep_file.yml does not — tests parsing is correct
    result = resolve_include("(hip_cargo.cabs)init.yml")
    assert result is not None
    assert result.name == "init.yml"


def test_resolve_include_no_parens():
    """Returns None for strings without parentheses."""
    assert resolve_include("no_parens.yml") is None


def test_resolve_include_empty_module():
    """Returns None for empty module in parens."""
    assert resolve_include("()empty.yml") is None


# --- parse_cab_yaml ---


def test_parse_cab_yaml_generate_cabs():
    """Parse hip-cargo's generate_cabs.yml cab definition."""
    path = resolve_include("(hip_cargo.cabs)generate_cabs.yml")
    schema = parse_cab_yaml(path)

    assert schema.name == "generate_cabs"
    assert "Generate Stimela cab definition" in schema.info
    assert "module" in schema.inputs
    assert schema.inputs["module"].dtype == "List[File]"
    assert schema.inputs["module"].required is True
    assert "output-dir" in schema.outputs
    assert schema.outputs["output-dir"].dtype == "Directory"


def test_parse_cab_yaml_init():
    """Parse the more complex init cab definition."""
    path = resolve_include("(hip_cargo.cabs)init.yml")
    schema = parse_cab_yaml(path)

    assert schema.inputs["project-name"].required is True
    assert schema.inputs["license-type"].choices == ["MIT", "Apache-2.0", "BSD-3-Clause"]
    assert schema.inputs["initial-version"].default == "0.0.0"


def test_parse_cab_yaml_invalid():
    """Raises ValueError for YAML without a cabs block."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.safe_dump({"not_cabs": {}}, f)
        path = f.name
    with pytest.raises(ValueError, match="No 'cabs' block"):
        parse_cab_yaml(path)
    Path(path).unlink()


# --- resolve_recipe_cabs ---


def test_resolve_recipe_cabs():
    """Resolves hip-cargo's own cabs from include strings."""
    includes = ["(hip_cargo.cabs)generate_cabs.yml", "(hip_cargo.cabs)init.yml"]
    result = resolve_recipe_cabs(includes)
    assert "generate_cabs" in result
    assert "init" in result


def test_resolve_recipe_cabs_skips_uninstalled():
    """Unresolvable cabs are silently skipped."""
    includes = [
        "(hip_cargo.cabs)generate_cabs.yml",
        "(nonexistent.package)foo.yml",
    ]
    result = resolve_recipe_cabs(includes)
    assert "generate_cabs" in result
    assert len(result) == 1


# --- CabSchema.to_dict ---


def test_cab_schema_to_dict():
    """to_dict produces JSON-serialisable output."""
    path = resolve_include("(hip_cargo.cabs)generate_cabs.yml")
    schema = parse_cab_yaml(path)
    d = schema.to_dict()
    serialized = json.dumps(d)
    roundtripped = json.loads(serialized)
    assert roundtripped["name"] == "generate_cabs"
    assert "module" in roundtripped["inputs"]


# --- parse_recipe with cab resolution ---


def test_parse_recipe_resolve_cabs_true_sara():
    """Sara's cabs (pfb_imaging) are not installed, but parsing still works."""
    dag = parse_recipe(FIXTURES / "sara.yml", resolve_cabs=True)
    # pfb_imaging is not installed, so cab_schemas should be empty
    assert dag.cab_schemas == {}
    # But the rest of the DAG should be correct
    assert len(dag.steps) == 5
    assert dag.name == "pfb-sara"


def test_parse_recipe_resolve_cabs_false():
    """With resolve_cabs=False, cab_schemas is empty and no resolution attempted."""
    dag = parse_recipe(FIXTURES / "sara.yml", resolve_cabs=False)
    assert dag.cab_schemas == {}
    assert len(dag.steps) == 5


def test_parse_recipe_resolves_hip_cargo_cabs():
    """Recipes referencing hip-cargo's own cabs are resolved."""
    recipe = {
        "_include": ["(hip_cargo.cabs)generate_cabs.yml"],
        "test_recipe": {
            "name": "test",
            "steps": {
                "step1": {
                    "cab": "generate_cabs",
                    "params": {"module": "=recipe.input_module"},
                }
            },
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.safe_dump(recipe, f)
        path = f.name

    dag = parse_recipe(path, resolve_cabs=True)
    assert "generate_cabs" in dag.cab_schemas
    step = dag.get_step("step1")
    assert step.cab_schema is not None
    assert step.cab_schema["name"] == "generate_cabs"
    Path(path).unlink()


# --- discover_project_cabs ---


def test_discover_project_cabs_hip_cargo():
    """Discovers hip-cargo's own cabs via hip_cargo.cli module path."""
    cabs = discover_project_cabs("hip_cargo.cli")
    names = [c["name"] for c in cabs]
    assert "generate_cabs" in names
    assert "init" in names


def test_discover_project_cabs_no_module(monkeypatch, tmp_path):
    """Returns empty list when no module and no matching pyproject.toml."""
    # Run from a temp dir with no pyproject.toml so the fallback doesn't find hip_cargo
    monkeypatch.chdir(tmp_path)
    assert discover_project_cabs("nonexistent.cli") == []
