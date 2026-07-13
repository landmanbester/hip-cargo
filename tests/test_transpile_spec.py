"""Tests for the transpile IR: data-edge inference, inmem detection, lowering."""

import sys
from pathlib import Path

import pytest

from hip_cargo.core.transpile import (
    TranspileRefusedError,
    build_recipe_spec,
    find_inmem,
    infer_data_edges,
    lower_interpolation,
)
from hip_cargo.monitoring.recipe_parser import parse_recipe

FIXTURES = Path(__file__).parent / "fixtures" / "transpile"
RECIPES = FIXTURES / "recipes"


@pytest.fixture(autouse=True)
def _fakepkg_on_path():
    sys.path.insert(0, str(FIXTURES))
    yield
    sys.path.remove(str(FIXTURES))


def _spec(recipe_name: str):
    dag = parse_recipe(RECIPES / recipe_name, resolve_cabs=True)
    return build_recipe_spec(dag, source=recipe_name)


# --- interpolation lowering ---


def test_lowering_plain_literal():
    assert lower_interpolation("just/a/path") == "'just/a/path'"


def test_lowering_single_ref_with_tail():
    assert lower_interpolation("{recipe.base-dir}/a.zarr") == 'f"{base_dir}/a.zarr"'


def test_lowering_multiple_refs():
    out = lower_interpolation("{recipe.base-dir}/{recipe.tag}.zarr")
    assert out == 'f"{base_dir}/{tag}.zarr"'


def test_lowering_escapes_literal_braces():
    assert lower_interpolation("{recipe.base-dir}/{notref}") == 'f"{base_dir}/{{notref}}"'


# --- inmem detection ---


def test_find_inmem_present():
    name, params = find_inmem("fakepkg.core.alpha.alpha")
    assert name == "alpha_inmem"
    assert params == ["memory_mode", "job_id", "pipeline_run_id", "work_dir", "n_items"]


def test_find_inmem_absent():
    assert find_inmem("fakepkg.core.delta.delta") is None


def test_find_inmem_unimportable_module():
    assert find_inmem("no.such.module.fn") is None


# --- edge inference ---


def test_data_edges_from_matched_paths():
    dag = parse_recipe(RECIPES / "linear_ok.yml", resolve_cabs=True)
    assert infer_data_edges(dag) == [("first", "second", "input-data")]


# --- full spec ---


def test_linear_spec_shape():
    spec = _spec("linear_ok.yml")
    assert spec.package == "fakepkg"
    assert spec.edges == (("first", "second"),)
    first, second = spec.steps

    assert first.inmem_func == "alpha_inmem"
    assert first.upstream is None
    assert first.work_dir_input == "base-dir"
    assert first.memory_mode.kind == "ref"
    assert first.kwargs == ()
    assert first.dropped == ("output",)

    assert second.inmem_func == "beta_inmem"
    assert second.upstream == "first"
    assert second.dropped == ("input-data", "output")
    assert [b.name for b in second.kwargs] == ["factor"]
    assert second.kwargs[0].as_python() == "factor"


def test_fallback_spec_uses_disk_command():
    spec = _spec("fallback.yml")
    first, second = spec.steps
    assert first.inmem_func == "alpha_inmem"
    assert second.inmem_func is None
    assert second.upstream == "first"
    assert second.func == "delta"
    # fallback keeps every binding, paths included, for the disk call
    assert sorted(b.name for b in second.all_bindings) == ["input-data", "output", "scale"]


def test_ambiguous_work_dir_refused(tmp_path):
    recipe = tmp_path / "ambiguous.yml"
    recipe.write_text(
        (RECIPES / "linear_ok.yml")
        .read_text()
        .replace(
            "    factor:\n      dtype: float\n      default: 2.0",
            "    factor:\n      dtype: float\n      default: 2.0\n"
            "    other-dir:\n      dtype: Directory\n      required: true",
        )
        .replace("output: '{recipe.base-dir}/a.zarr'", "output: '{recipe.other-dir}/a.zarr'")
        .replace("input-data: '{recipe.base-dir}/a.zarr'", "input-data: '{recipe.other-dir}/a.zarr'")
    )
    dag = parse_recipe(recipe, resolve_cabs=True)
    with pytest.raises(TranspileRefusedError) as exc:
        build_recipe_spec(dag)
    features = [e.feature for e in exc.value.errors]
    assert "ambiguous-work-dir" in features
