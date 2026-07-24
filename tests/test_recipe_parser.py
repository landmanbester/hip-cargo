"""Tests for the stimela recipe parser."""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from hip_cargo.monitoring.recipe_parser import (
    RecipeDAG,
    find_recipe_block,
    parse_param_binding,
    parse_recipe,
)

FIXTURES = Path(__file__).parent / "fixtures"
SARA_YML = FIXTURES / "sara.yml"


@pytest.fixture
def sara_dag() -> RecipeDAG:
    """Parse the sara fixture once for reuse across tests."""
    return parse_recipe(SARA_YML)


def test_parse_sara_recipe(sara_dag: RecipeDAG):
    """Parse sara.yml and verify top-level DAG structure."""
    assert sara_dag.name == "pfb-sara"
    assert sara_dag.recipe_key == "gosara"
    assert len(sara_dag.steps) == 5
    assert sara_dag.step_names() == ["initialize", "gridimage", "saradeconv", "restoreimage", "degridimage"]
    assert [s.cab for s in sara_dag.steps] == ["init", "grid", "sara", "restore", "degrid"]
    assert len(sara_dag.edges) == 4
    assert sara_dag.edges == [
        ("initialize", "gridimage"),
        ("gridimage", "saradeconv"),
        ("saradeconv", "restoreimage"),
        ("restoreimage", "degridimage"),
    ]


def test_recipe_inputs_parsing(sara_dag: RecipeDAG):
    """Verify recipe-level inputs are parsed correctly."""
    assert len(sara_dag.inputs) == 36

    inputs_by_name = {i.name: i for i in sara_dag.inputs}

    ms = inputs_by_name["ms"]
    assert ms.dtype == "List[URI]"
    assert ms.required is True

    niter = inputs_by_name["niter"]
    assert niter.dtype == "int"
    assert niter.default == 15

    overwrite = inputs_by_name["overwrite"]
    assert overwrite.aliases == ["*.overwrite"]

    base_dir = inputs_by_name["base-dir"]
    assert base_dir.mkdir is True


def test_step_param_bindings_initialize(sara_dag: RecipeDAG):
    """Verify parameter bindings for the initialize step."""
    step = sara_dag.get_step("initialize")
    assert step is not None
    params_by_name = {p.name: p for p in step.params}

    ms = params_by_name["ms"]
    assert ms.is_binding is True
    assert ms.binding_expr == "recipe.ms"
    assert ms.recipe_refs == ["recipe.ms"]

    gain_table = params_by_name["gain-table"]
    assert gain_table.is_binding is True
    assert gain_table.binding_expr == "IFSET(recipe.gains)"
    assert gain_table.recipe_refs == ["recipe.gains"]

    check_ants = params_by_name["check-ants"]
    assert check_ants.is_binding is False
    assert check_ants.value is False

    cpi = params_by_name["channels-per-image"]
    assert cpi.recipe_refs == ["recipe.channels-per-image"]


def test_saradeconv_step_params(sara_dag: RecipeDAG):
    """Verify parameter bindings for the saradeconv step."""
    step = sara_dag.get_step("saradeconv")
    assert step is not None
    params_by_name = {p.name: p for p in step.params}

    assert params_by_name["niter"].is_binding is True
    assert "recipe.niter" in params_by_name["niter"].recipe_refs

    assert params_by_name["bases"].is_binding is False
    assert params_by_name["bases"].value == "self,db1,db2,db3"

    assert params_by_name["nlevels"].value == 2

    assert params_by_name["pd-tol"].value == pytest.approx(1.5e-4)

    positivity = params_by_name["positivity"]
    assert positivity.is_binding is True
    assert "recipe.product" in positivity.recipe_refs

    nthreads = params_by_name["nthreads"]
    assert nthreads.is_binding is True
    assert "recipe.nworkers" in nthreads.recipe_refs
    assert "recipe.nthreads" in nthreads.recipe_refs


def test_includes(sara_dag: RecipeDAG):
    """Verify the _include entries are captured."""
    assert len(sara_dag.includes) == 5
    assert "(pfb_imaging.cabs)init.yml" in sara_dag.includes
    assert "(pfb_imaging.cabs)degrid.yml" in sara_dag.includes


def test_to_dict_round_trip(sara_dag: RecipeDAG):
    """Verify to_dict() produces a JSON-serializable dict."""
    d = sara_dag.to_dict()
    # Should be JSON-serializable
    serialized = json.dumps(d)
    roundtripped = json.loads(serialized)
    assert roundtripped["name"] == "pfb-sara"
    assert roundtripped["recipe_key"] == "gosara"
    assert len(roundtripped["steps"]) == 5
    assert len(roundtripped["edges"]) == 4
    assert len(roundtripped["inputs"]) == 36


def test_find_recipe_block():
    """Verify find_recipe_block skips _include and opts."""
    parsed = {
        "_include": ["foo.yml"],
        "opts": {"log": {}},
        "my_recipe": {"name": "test", "steps": {}},
    }
    key, block = find_recipe_block(parsed)
    assert key == "my_recipe"
    assert block["name"] == "test"


def test_find_recipe_block_no_recipe():
    """Verify find_recipe_block raises on missing recipe."""
    with pytest.raises(ValueError, match="No recipe block found"):
        find_recipe_block({"_include": [], "opts": {}})


def test_minimal_recipe():
    """Test with a minimal recipe: one step, no inputs."""
    minimal = {
        "simple": {
            "name": "minimal",
            "steps": {
                "only_step": {
                    "cab": "my_cab",
                    "params": {"x": 42},
                }
            },
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.safe_dump(minimal, f)
        path = f.name

    dag = parse_recipe(path)
    assert dag.name == "minimal"
    assert dag.recipe_key == "simple"
    assert len(dag.steps) == 1
    assert dag.steps[0].cab == "my_cab"
    assert len(dag.inputs) == 0
    assert len(dag.edges) == 0
    Path(path).unlink()


def test_recipe_with_no_steps():
    """Verify graceful handling of a recipe with no steps."""
    no_steps = {
        "empty": {
            "name": "no-steps",
            "inputs": {"x": {"dtype": "int"}},
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        yaml.safe_dump(no_steps, f)
        path = f.name

    dag = parse_recipe(path)
    assert dag.name == "no-steps"
    assert len(dag.steps) == 0
    assert len(dag.edges) == 0
    assert len(dag.inputs) == 1
    Path(path).unlink()


def test_parse_param_binding_literal():
    """Literal values are not bindings."""
    p = parse_param_binding("x", 42)
    assert p.is_binding is False
    assert p.value == 42
    assert p.recipe_refs == []


def test_parse_param_binding_recipe_ref():
    """Simple recipe reference is parsed correctly."""
    p = parse_param_binding("ms", "=recipe.ms")
    assert p.is_binding is True
    assert p.binding_expr == "recipe.ms"
    assert p.recipe_refs == ["recipe.ms"]


def test_parse_param_binding_ifset():
    """IFSET binding extracts recipe refs."""
    p = parse_param_binding("gains", "=IFSET(recipe.gains)")
    assert p.is_binding is True
    assert p.binding_expr == "IFSET(recipe.gains)"
    assert p.recipe_refs == ["recipe.gains"]


def test_parse_param_binding_expression():
    """Arithmetic expression extracts multiple recipe refs."""
    p = parse_param_binding("nthreads", "=recipe.nworkers * recipe.nthreads")
    assert p.is_binding is True
    assert p.recipe_refs == ["recipe.nworkers", "recipe.nthreads"]


def test_get_step_not_found(sara_dag: RecipeDAG):
    """get_step returns None for unknown step names."""
    assert sara_dag.get_step("nonexistent") is None
