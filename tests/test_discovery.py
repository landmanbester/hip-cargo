"""Tests for command and recipe discovery."""

from pathlib import Path

import pytest

from hip_cargo.monitoring.discovery import discover_commands
from hip_cargo.monitoring.recipe_discovery import discover_recipes, find_recipe

FIXTURES = Path(__file__).parent / "fixtures"


def test_discover_commands_no_module():
    """Returns empty list when no CLI module is available."""
    assert discover_commands() == []


def test_discover_commands_invalid_module():
    """Returns empty list when CLI module can't be imported."""
    assert discover_commands("nonexistent.module.path") == []


def test_discover_recipes_with_fixture_dir():
    """Finds sara.yml in the fixtures directory."""
    recipes = discover_recipes(FIXTURES)
    names = [r["name"] for r in recipes]
    assert "sara" in names


def test_discover_recipes_missing_dir():
    """Returns empty list for a nonexistent directory."""
    assert discover_recipes("/nonexistent/path") == []


def test_discover_recipes_none_defaults():
    """Returns a list (possibly empty) when no dir is specified."""
    result = discover_recipes()
    assert isinstance(result, list)


def test_find_recipe_existing():
    """Returns correct Path for an existing recipe."""
    path = find_recipe("sara", FIXTURES)
    assert path.name == "sara.yml"
    assert path.exists()


def test_find_recipe_missing():
    """Raises FileNotFoundError for a nonexistent recipe."""
    with pytest.raises(FileNotFoundError, match="not found"):
        find_recipe("nonexistent", FIXTURES)
