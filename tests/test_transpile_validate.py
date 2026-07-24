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


def _mutate_linear(tmp_path, replacements):
    recipe = tmp_path / "mutated.yml"
    text = (RECIPES / "linear_ok.yml").read_text()
    for old, new in replacements:
        assert old in text
        text = text.replace(old, new)
    recipe.write_text(text)
    dag = parse_recipe(recipe, resolve_cabs=True)
    return validate_recipe(dag)


def test_unsafe_step_name_refused(tmp_path):
    errors = _mutate_linear(tmp_path, [("    first:", '    "ev!l; name":')])
    assert "unsafe-name" in [e.feature for e in errors]


def test_keyword_step_name_refused(tmp_path):
    errors = _mutate_linear(tmp_path, [("    first:", "    class:")])
    assert "unsafe-name" in [e.feature for e in errors]


def test_hyphen_underscore_collision_refused(tmp_path):
    errors = _mutate_linear(
        tmp_path,
        [
            (
                "    factor:\n      dtype: float\n      default: 2.0",
                "    my-x:\n      dtype: float\n      default: 2.0\n    my_x:\n      dtype: float\n      default: 3.0",
            )
        ],
    )
    assert "name-collision" in [e.feature for e in errors]


def test_reserved_input_name_refused(tmp_path):
    errors = _mutate_linear(
        tmp_path,
        [
            (
                "    factor:\n      dtype: float\n      default: 2.0",
                "    monitor:\n      dtype: bool\n      default: false",
            )
        ],
    )
    assert "reserved-name" in [e.feature for e in errors]


def test_unsupported_default_type_refused(tmp_path):
    errors = _mutate_linear(
        tmp_path,
        [
            (
                "    factor:\n      dtype: float\n      default: 2.0",
                "    when:\n      dtype: str\n      default: 2026-01-01",
            )
        ],
    )
    assert "unsupported-default" in [e.feature for e in errors]
