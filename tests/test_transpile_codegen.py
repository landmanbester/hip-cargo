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


def test_hostile_strings_emitted_inert(tmp_path):
    """Injection attempt in defaults/info must survive as plain data, not code."""
    import importlib.util
    import inspect

    import yaml

    hostile_default = '", __import__("os").system("echo pwned"), "'
    hostile_info = 'quotes " and \\ backslash {braces} \n newline'
    recipe = {
        "_include": ["(fakepkg.cabs)alpha.yml"],
        "demo": {
            "name": "demo",
            "inputs": {
                "base-dir": {"dtype": "Directory", "required": True, "mkdir": True},
                "payload": {"dtype": "str", "default": hostile_default, "info": hostile_info},
            },
            "steps": {
                "first": {"cab": "alpha", "params": {"output": "{recipe.base-dir}/a.zarr"}},
            },
        },
    }
    recipe_path = tmp_path / "hostile.yml"
    recipe_path.write_text(yaml.safe_dump(recipe))

    out = tmp_path / "transpiled"
    transpile_recipe(recipe_path, out, out_package="fakepkg.transpiled")

    import py_compile

    for module in out.glob("*.py"):
        py_compile.compile(str(module), doraise=True)

    spec = importlib.util.spec_from_file_location("hostile_cli", out / "cli.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # would execute injected code if escaping failed
    default = inspect.signature(mod.run).parameters["payload"].default
    assert default == hostile_default


@pytest.mark.slow
def test_generated_pipeline_executes_on_ray(tmp_path):
    """The emitted package actually runs on a local Ray cluster."""
    ray = pytest.importorskip("ray")
    from hip_cargo.utils.progress import NullBackend, ProgressEvent, set_backend

    class ListBackend:
        def __init__(self):
            self.events: list[ProgressEvent] = []

        def emit(self, event):
            self.events.append(event)

        def close(self):
            pass

    out = tmp_path / "genpkg"
    transpile_recipe(RECIPES / "linear_ok.yml", out, out_package="genpkg")
    sys.path.insert(0, str(tmp_path))
    backend = ListBackend()
    try:
        ray.init(
            num_cpus=2,
            ignore_reinit_error=True,
            runtime_env={"env_vars": {"PYTHONPATH": f"{FIXTURES}:{tmp_path}"}},
        )
        import genpkg.runner as runner

        set_backend(backend)
        job_id, final_ref = runner.run_pipeline(base_dir=str(tmp_path / "work"), factor=3.0)
        assert ray.get(tasks_check(ray, final_ref, out)) is True
        types = [e.event_type for e in backend.events]
        assert types.count("step_completed") == 2
        assert types[-1] == "completed"
    finally:
        set_backend(NullBackend())
        sys.path.remove(str(tmp_path))
        ray.shutdown()


def tasks_check(ray, ref, out):
    """Resolve the final ref through the generated probe (driver stays light)."""
    import importlib

    tasks = importlib.import_module("genpkg.tasks")
    return tasks._check.remote([ref])


@pytest.mark.slow
def test_generated_pipeline_surfaces_step_failure(tmp_path):
    """A crashing step emits STEP_FAILED + FAILED and raises (no silent exit 0)."""
    ray = pytest.importorskip("ray")
    from hip_cargo.utils.progress import NullBackend, ProgressEvent, set_backend

    class ListBackend:
        def __init__(self):
            self.events: list[ProgressEvent] = []

        def emit(self, event):
            self.events.append(event)

        def close(self):
            pass

    out = tmp_path / "failpkg"
    transpile_recipe(RECIPES / "failing.yml", out, out_package="failpkg")
    sys.path.insert(0, str(tmp_path))
    backend = ListBackend()
    try:
        ray.init(
            num_cpus=2,
            ignore_reinit_error=True,
            runtime_env={"env_vars": {"PYTHONPATH": f"{FIXTURES}:{tmp_path}"}},
        )
        import failpkg.runner as runner

        set_backend(backend)
        with pytest.raises(Exception, match="omega always fails"):
            runner.run_pipeline(base_dir=str(tmp_path / "work"))
        types = [e.event_type for e in backend.events]
        assert "step_failed" in types
        assert types[-1] == "failed"
        failed = next(e for e in backend.events if e.event_type == "step_failed")
        assert failed.worker_name == "second"
    finally:
        set_backend(NullBackend())
        sys.path.remove(str(tmp_path))
        ray.shutdown()
