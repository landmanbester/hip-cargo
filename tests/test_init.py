"""Tests for the hip-cargo init command."""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Each Python template and where init writes it.
PY_TEMPLATES = {
    "cli_single.py": "src/{pkg}/cli/__init__.py",
    "cli_multi.py": "src/{pkg}/cli/__init__.py",
    "onboard_cli.py": "src/{pkg}/cli/onboard.py",
    "onboard_core.py": "src/{pkg}/core/onboard.py",
    "test_roundtrip.py": "tests/test_roundtrip.py",
    "test_precommit.py": "tests/test_precommit.py",
}


@pytest.mark.parametrize("template", sorted(PY_TEMPLATES))
@pytest.mark.parametrize("pkg", ["demo", "pfb_model_spec"])
def test_python_template_is_already_ruff_clean(tmp_path: Path, template: str, pkg: str) -> None:
    """A template must pass the scaffold's own ruff without being rewritten.

    hip-cargo's ruff excludes ``templates/``, and ``init`` reformats the
    scaffold afterwards, so neither notices a template ruff would change. A
    repo that copies a template in (e.g. to adopt the round-trip test) would.
    """
    from hip_cargo.core.init import TEMPLATES_DIR, _apply_substitutions

    subs = {
        "<PACKAGE_NAME>": pkg,
        "<PROJECT_NAME>": pkg.replace("_", "-"),
        "<CLI_COMMAND>": pkg.replace("_", "-"),
        "<DESCRIPTION>": "A demo package",
    }
    pyproject = re.sub(
        r"<[A-Z][A-Z_]+>", "x", _apply_substitutions((TEMPLATES_DIR / "pyproject.toml").read_text(), subs)
    )
    (tmp_path / "pyproject.toml").write_text(pyproject)
    for package in (f"src/{pkg}", f"src/{pkg}/cli", f"src/{pkg}/core", "tests"):
        (tmp_path / package).mkdir(parents=True, exist_ok=True)
        (tmp_path / package / "__init__.py").touch()
    target = tmp_path / PY_TEMPLATES[template].format(pkg=pkg)
    target.write_text(_apply_substitutions((TEMPLATES_DIR / template).read_text(), subs))
    relative = str(target.relative_to(tmp_path))

    for command in (["ruff", "format", "--diff", relative], ["ruff", "check", "--no-fix", relative]):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 0, f"{template}: `{' '.join(command)}` failed:\n{result.stdout}{result.stderr}"


@pytest.mark.slow
def test_init_produces_clean_project():
    """Verify that hip-cargo init generates a project that passes ruff format and lint checks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test-proj"

        # Run hip-cargo init
        from hip_cargo.core.init import init

        init(
            project_name="test-proj",
            github_user="testuser",
            description="A test project",
            project_dir=project_dir,
        )

        # Verify critical scaffold files exist
        pkg = "test_proj"
        expected_files = [
            "pyproject.toml",
            "tbump.toml",
            "Dockerfile",
            "CLAUDE.md",
            ".gitignore",
            ".pre-commit-config.yaml",
            "LICENSE",
            "README.md",
            ".github/dependabot.yml",
            ".github/workflows/ci.yml",
            ".github/workflows/publish.yml",
            ".github/workflows/publish-container.yml",
            ".github/workflows/update-cabs.yml",
            ".devcontainer/devcontainer.json",
            f"src/{pkg}/__init__.py",
            f"src/{pkg}/cli/__init__.py",
            f"src/{pkg}/cli/onboard.py",
            f"src/{pkg}/core/__init__.py",
            f"src/{pkg}/core/onboard.py",
            f"src/{pkg}/cabs/__init__.py",
            "tests/__init__.py",
            "tests/test_install.py",
            "tests/test_roundtrip.py",
            "tests/test_precommit.py",
        ]
        for filepath in expected_files:
            assert (project_dir / filepath).exists(), f"Missing scaffold file: {filepath}"

        # GPU / RUN_ARGS knobs are scaffolded (commented) for discoverability.
        container_image = (project_dir / f"src/{pkg}/_container_image.py").read_text()
        assert "CONTAINER_IMAGE = " in container_image
        assert "# GPU = True" in container_image
        assert "RUN_ARGS_APPTAINER" in container_image

        # Markdown is excluded from ruff so the aligned comments in CLAUDE.md survive (#95).
        assert 'extend-exclude = ["*.md"]' in (project_dir / "pyproject.toml").read_text()
        assert "GPU = True                  #" in (project_dir / ".claude/rules/architecture.md").read_text()

        # Every template placeholder is substituted, and hip-cargo is floored at this release.
        from hip_cargo import __version__

        for path in project_dir.rglob("*"):
            if path.is_file() and ".git" not in path.parts and ".venv" not in path.parts:
                leftover = re.findall(r"<[A-Z][A-Z_]+>", path.read_text(errors="ignore"))
                assert not leftover, f"Unsubstituted placeholders in {path}: {leftover}"
        assert f'"hip-cargo>={__version__}"' in (project_dir / "pyproject.toml").read_text()

        # CI matrix legs must run on their own interpreter, not .python-version (#97).
        assert "UV_PYTHON: ${{ matrix.python-version }}" in (project_dir / ".github/workflows/ci.yml").read_text()

        # Verify ruff format check passes (no files would be reformatted)
        result = subprocess.run(
            ["uv", "run", "ruff", "format", "--check", "."],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"ruff format check failed:\n{result.stdout}\n{result.stderr}"

        # Verify ruff lint check passes
        result = subprocess.run(
            ["uv", "run", "ruff", "check", "."],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"ruff lint check failed:\n{result.stdout}\n{result.stderr}"

        # The scaffold's own suite (round-trip in both directions) must pass. Install
        # this checkout over the released hip-cargo the scaffold resolved, since the
        # templates are generated by this version's emitter.
        repo_root = Path(__file__).resolve().parents[1]
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        subprocess.run(
            ["uv", "pip", "install", "--python", ".venv", str(repo_root)],
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        result = subprocess.run(
            ["uv", "run", "--no-sync", "pytest", "-q", "tests"],
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"scaffold test suite failed:\n{result.stdout}\n{result.stderr}"


def test_pin_precommit_ruff_uses_the_locked_version(tmp_path: Path) -> None:
    """A fresh scaffold's ruff hook must match the ruff uv locked, not the template's rev (#119)."""
    from hip_cargo.core.init import _pin_precommit_ruff

    (tmp_path / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "rich"\nversion = "14.0.0"\n\n'
        '[[package]]\nname = "ruff"\nversion = "0.17.5"\nsource = { registry = "https://pypi.org/simple" }\n'
    )
    config = tmp_path / ".pre-commit-config.yaml"
    config.write_text(
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    rev: v0.16.8\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v5.0.0\n"
    )

    _pin_precommit_ruff(tmp_path)

    text = config.read_text()
    assert "    rev: v0.17.5\n  - repo: https://github.com/pre-commit/pre-commit-hooks\n    rev: v5.0.0\n" in text


def _contract_project(tmp_path: Path, core_source: str | None, register: bool) -> Path:
    """A one-command project with a generated wrapper, for the template's contract checks."""
    from hip_cargo.core.generate_function import generate_function
    from hip_cargo.core.init import TEMPLATES_DIR, _apply_substitutions

    pkg = tmp_path / "src" / "demo"
    for sub in ("cli", "core", "cabs"):
        (pkg / sub).mkdir(parents=True)
        (pkg / sub / "__init__.py").touch()
    (pkg / "__init__.py").touch()
    (pkg / "cabs" / "run.yml").write_text(
        "cabs:\n"
        "  run:\n"
        "    info: Run it\n"
        "    command: demo.core.run.run\n"
        "    image: ghcr.io/example/demo:latest\n"
        "    inputs:\n"
        "      x: {dtype: int, required: true, info: X}\n"
        "      y: {dtype: str, default: a, info: Y}\n"
        "    outputs: {}\n"
    )
    generate_function(pkg / "cabs" / "run.yml", output_file=pkg / "cli" / "run.py")
    if core_source is not None:
        (pkg / "core" / "run.py").write_text(core_source)
    registration = 'app.command(name="run")(run)\n' if register else ""
    (pkg / "cli" / "__init__.py").write_text(
        f"import typer\n\napp = typer.Typer()\n\nfrom demo.cli.run import run  # noqa: E402\n\n{registration}"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    subs = {"<PACKAGE_NAME>": "demo"}
    (tests / "test_roundtrip.py").write_text(
        _apply_substitutions((TEMPLATES_DIR / "test_roundtrip.py").read_text(), subs)
    )
    return tmp_path


def _core(signature: str) -> str:
    return f"def run({signature}):\n    pass\n"


@pytest.mark.parametrize(
    ("core_source", "register", "outcome"),
    [
        (_core("x, y='a'"), True, "2 passed"),
        (_core("x, **kwargs"), True, "2 passed"),
        ("from demo.core._impl import run  # noqa: F401\n", True, "1 passed, 1 skipped"),
        ("from collections.abc import Callable\n\nrun: Callable[..., None] = print\n", True, "1 passed, 1 skipped"),
        (
            "try:\n    from demo.core._fast import run\nexcept ImportError:\n\n    def run(x, y='a'):\n        pass\n",
            True,
            "1 passed, 1 skipped",
        ),
        ("from collections.abc import Callable\n\nrun: Callable[..., None]\n", True, "which does not define it"),
        ("if True:\n\n    def run(x, y='a'):\n        pass\n", True, "2 passed"),
        (_core("x, y, z"), True, "requires ['z']"),
        (_core("x"), True, "does not accept ['y']"),
        (_core("x, /, y='a'"), True, "positional-only"),
        (None, True, "imports run from demo.core.run, which does not exist"),
        (_core("x, y='a'").replace("def run", "def walk"), True, "which does not define it"),
        (_core("x, y='a'"), False, "not registered in cli/__init__.py: ['run']"),
    ],
    ids=[
        "binds",
        "var-kwargs",
        "re-exported",
        "annotated-alias",
        "conditional",
        "bare-annotation",
        "nested-def",
        "missing-required",
        "unexpected",
        "positional-only",
        "stale-module",
        "stale-function",
        "unregistered",
    ],
)
def test_template_contract_checks_fail_on_a_broken_contract(
    tmp_path: Path, core_source: str | None, register: bool, outcome: str
) -> None:
    """The scaffold only exercises ``onboard`` (no parameters, registered), so prove the checks can fail."""
    project = _contract_project(tmp_path, core_source, register)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_roundtrip.py",
            "-k",
            "core_function or registered",
        ],
        cwd=project,
        env={**os.environ, "PYTHONPATH": str(project / "src")},
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode == (0 if "passed" in outcome else 1), output
    assert outcome in output, output
