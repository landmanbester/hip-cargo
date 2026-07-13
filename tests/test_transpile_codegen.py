"""Tests for transpile codegen: golden output, idempotence, lint cleanliness."""

import subprocess
import sys
from pathlib import Path

import pytest

from hip_cargo.core.transpile import TranspileRefusedError, transpile_recipe

FIXTURES = Path(__file__).parent / "fixtures" / "transpile"
RECIPES = FIXTURES / "recipes"
GOLDEN = FIXTURES / "golden"
MODULES = ["__init__.py", "tasks.py", "runner.py", "cli.py"]


@pytest.fixture(autouse=True)
def _fakepkg_on_path():
    sys.path.insert(0, str(FIXTURES))
    yield
    sys.path.remove(str(FIXTURES))


def test_golden_output(tmp_path):
    """Generated modules match the reviewed golden files byte-for-byte."""
    out = tmp_path / "transpiled"
    transpile_recipe(RECIPES / "linear_ok.yml", out, out_package="fakepkg.transpiled")

    def _normalise(text: str) -> str:
        # The header records the recipe path as passed in; compare by basename.
        return "\n".join(
            "# Source recipe: linear_ok.yml" if line.startswith("# Source recipe:") else line
            for line in text.splitlines()
        )

    for name in MODULES:
        assert _normalise((out / name).read_text()) == _normalise((GOLDEN / name).read_text()), (
            f"{name} drifted from golden"
        )


def test_idempotent_rewrite(tmp_path):
    out = tmp_path / "transpiled"
    first = transpile_recipe(RECIPES / "linear_ok.yml", out, out_package="fakepkg.transpiled")
    assert len(first) == len(MODULES)
    mtimes = {p.name: p.stat().st_mtime_ns for p in out.glob("*.py")}
    second = transpile_recipe(RECIPES / "linear_ok.yml", out, out_package="fakepkg.transpiled")
    assert second == []
    assert {p.name: p.stat().st_mtime_ns for p in out.glob("*.py")} == mtimes


def test_generated_code_is_ruff_clean(tmp_path):
    out = tmp_path / "transpiled"
    transpile_recipe(RECIPES / "linear_ok.yml", out, out_package="fakepkg.transpiled")
    result = subprocess.run(
        ["ruff", "check", str(out), "--config", str(Path(__file__).parents[1] / "pyproject.toml")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


def test_generated_code_is_bandit_clean(tmp_path):
    pytest.importorskip("bandit")
    out = tmp_path / "transpiled"
    transpile_recipe(RECIPES / "linear_ok.yml", out, out_package="fakepkg.transpiled")
    result = subprocess.run(
        [sys.executable, "-m", "bandit", "-q", "-r", str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_modules_compile(tmp_path):
    import py_compile

    out = tmp_path / "transpiled"
    transpile_recipe(RECIPES / "fallback.yml", out, out_package="fakepkg.transpiled")
    for module in out.glob("*.py"):
        py_compile.compile(str(module), doraise=True)
    tasks_src = (out / "tasks.py").read_text()
    # fallback consumer calls the disk command with every binding, paths included
    assert "from fakepkg.core.delta import delta" in tasks_src
    assert "input_data=input_data" in tasks_src


def test_refused_recipe_raises_with_all_errors(tmp_path):
    with pytest.raises(TranspileRefusedError) as exc:
        transpile_recipe(RECIPES / "formula.yml", tmp_path / "x")
    assert "formula-dsl" in str(exc.value)
    assert not (tmp_path / "x").exists()
