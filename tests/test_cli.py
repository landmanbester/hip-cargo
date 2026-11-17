"""Test CLI functionality."""

import tempfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from hip_cargo.cli import app


@pytest.fixture
def runner():
    """Test runner for CLI commands."""
    return CliRunner()


class TestCLI:
    """Test CLI functionality."""

    @pytest.mark.integration
    def test_cli_help(self, runner):
        """Test CLI help command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "hip-cargo" in result.stdout

    @pytest.mark.integration
    def test_generate_command_help(self, runner):
        """Test generate-cab command help."""
        result = runner.invoke(app, ["generate-cabs", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.stdout.lower()

    @pytest.mark.integration
    def test_generate_nonexistent_file(self, runner):
        """Test generate-cabs command with nonexistent module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            result = runner.invoke(
                app, ["generate-cabs", "--module", "nonexistent_module.py", "--output-dir", str(output)]
            )
            assert result.exit_code != 0

    @pytest.mark.integration
    def test_generate_invalid_function(self, runner):
        """Test generate-cabs command with module that has no decorated function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            # Use a module that exists but has no @stimela_cab
            result = runner.invoke(
                app,
                ["generate-cabs", "--module", "src/hip_cargo/utils/introspector.py", "--output-dir", str(output_dir)],
            )
            # Currently succeeds even with no decorated functions (silently skips)
            # TODO: Should this error out instead?
            assert result.exit_code == 0
            # Verify no cab files were created
            cab_files = list(Path(output_dir).glob("*.yml"))
            assert len(cab_files) == 0

    @pytest.mark.integration
    def test_generate_image_override(self, runner):
        """Test that --image overrides the pyproject.toml-resolved image."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            custom_image = "registry.example.com/my-image:v1.2.3"
            result = runner.invoke(
                app,
                [
                    "generate-cabs",
                    "--module",
                    "src/hip_cargo/cli/generate_cabs.py",
                    "--image",
                    custom_image,
                    "--output-dir",
                    str(output_dir),
                ],
            )
            assert result.exit_code == 0
            output_file = output_dir / "generate_cabs.yml"
            assert output_file.exists()
            cab = yaml.safe_load(output_file.read_text())
            assert cab["cabs"]["generate_cabs"]["image"] == custom_image
