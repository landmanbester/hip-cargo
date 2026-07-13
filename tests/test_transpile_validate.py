"""Tests for the transpile restricted-subset validator."""

import sys
from pathlib import Path

import pytest

from hip_cargo.core.transpile import validate_recipe
from hip_cargo.monitoring.recipe_parser import parse_recipe

FIXTURES = Path(__file__).parent / "fixtures" / "transpile"
RECIPES = FIXTURES / "recipes"


@pytest.fixture(autouse=True)
def _fakepkg_on_path():
    """Make the fixture package importable for cab resolution."""
    sys.path.insert(0, str(FIXTURES))
    yield
    sys.path.remove(str(FIXTURES))


def _validate(recipe_name: str):
    dag = parse_recipe(RECIPES / recipe_name, resolve_cabs=True)
    return validate_recipe(dag)


def test_linear_recipe_is_clean():
    assert _validate("linear_ok.yml") == []


def test_fallback_recipe_is_clean():
    assert _validate("fallback.yml") == []


def test_formula_dsl_refused():
    errors = _validate("formula.yml")
    assert [e.feature for e in errors] == ["formula-dsl"]
    assert "param 'n-items'" in errors[0].location
    assert "=IF" in errors[0].message or "formula DSL" in errors[0].message


def test_aliases_refused():
    errors = _validate("alias.yml")
    assert [e.feature for e in errors] == ["aliases"]
    assert "input 'out'" in errors[0].location


def test_for_loop_refused():
    errors = _validate("loop.yml")
    assert [e.feature for e in errors] == ["for_loop"]
    assert "step 'first'" in errors[0].location


def test_unknown_refs_refused_in_binding_and_interpolation():
    errors = _validate("unknown_ref.yml")
    features = sorted(e.feature for e in errors)
    assert features == ["unknown-ref", "unknown-ref"]
    messages = " | ".join(e.message for e in errors)
    assert "no-such-input" in messages
    assert "also-missing" in messages


def test_unbound_required_refused():
    errors = _validate("unbound_required.yml")
    assert [e.feature for e in errors] == ["unbound-required"]
    assert "'scale'" in errors[0].message
    assert "delta" in errors[0].message


def test_errors_are_collected_not_first_fail(tmp_path):
    """A recipe with several violations reports all of them."""
    recipe = tmp_path / "multi.yml"
    recipe.write_text(
        (RECIPES / "formula.yml")
        .read_text()
        .replace("cab: alpha", "cab: alpha\n      for_loop:\n        var: x\n        over: [1]")
    )
    dag = parse_recipe(recipe, resolve_cabs=True)
    errors = validate_recipe(dag)
    assert sorted(e.feature for e in errors) == ["for_loop", "formula-dsl"]
