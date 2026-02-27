"""Tests for the hip-cargo init command."""

import subprocess
import tempfile
from pathlib import Path

import pytest


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
            ".gitignore",
            ".pre-commit-config.yaml",
            "LICENSE",
            "README.md",
            "scripts/generate_cabs.py",
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
        ]
        for filepath in expected_files:
            assert (project_dir / filepath).exists(), f"Missing scaffold file: {filepath}"

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
