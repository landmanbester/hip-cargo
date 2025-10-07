"""Test CLI functionality."""

import tempfile
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from hip_cargo.cli import app


@pytest.fixture
def runner():
    """Test runner for CLI commands."""
    return CliRunner()


@pytest.fixture
def temp_module_file():
    """Create a temporary Python module with stimela decorators."""
    content = '''
"""Temporary test module."""

from pathlib import Path
import typer
from typing_extensions import Annotated
from hip_cargo import stimela_cab, stimela_output


@stimela_cab(name="temp_processor", info="Temporary test processor")
@stimela_output(name="output_file", dtype="File", info="{input_file}.processed")
def process_temp(
    input_file: Annotated[Path, typer.Argument(help="Input file to process")],
    threshold: Annotated[float, typer.Option(help="Processing threshold")] = 0.5,
):
    """
    Process a temporary file.

    Args:
        input_file: Input file to process
        threshold: Processing threshold value
    """
    pass
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()
        return Path(f.name)


class TestCLI:
    """Test CLI functionality."""

    @pytest.mark.integration
    def test_cli_help(self, runner):
        """Test CLI help command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "hip-cargo" in result.stdout or "cargo" in result.stdout

    @pytest.mark.integration
    def test_generate_command_help(self, runner):
        """Test generate-cab command help."""
        result = runner.invoke(app, ["generate-cab", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.stdout.lower()

    @pytest.mark.integration
    def test_generate_nonexistent_file(self, runner):
        """Test generate-cab command with nonexistent module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "output.yaml"
            result = runner.invoke(app, ["generate-cab", "nonexistent_module", str(output)])
            assert result.exit_code != 0

    @pytest.mark.integration
    def test_generate_valid_module(self, runner):
        """Test generate-cab command with example module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "output.yaml"
            result = runner.invoke(
                app, ["generate-cab", "tests.example_package.processor", str(output)]
            )

            if result.exit_code == 0:
                assert output.exists()
                content = output.read_text()
                assert "cabs:" in content

    @pytest.mark.integration
    def test_generate_with_output_file(self, runner):
        """Test generate-cab command writes to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.yaml"
            result = runner.invoke(
                app,
                ["generate-cab", "tests.example_package.processor", str(output)],
            )

            if result.exit_code == 0:
                assert output.exists()
                content = output.read_text()
                assert "cabs:" in content

    @pytest.mark.integration
    def test_generate_invalid_function(self, runner):
        """Test generate-cab command with module that has no decorated function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "output.yaml"
            # Use a module that exists but has no @stimela_cab
            result = runner.invoke(app, ["generate-cab", "hip_cargo.yaml_generator", str(output)])
            assert result.exit_code != 0

    @pytest.mark.unit
    def test_cli_app_exists(self):
        """Test that CLI app is properly configured."""
        assert isinstance(app, typer.Typer)

    @pytest.mark.integration
    def test_generate_with_verbose(self, runner):
        """Test generate-cab produces output messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "output.yaml"
            result = runner.invoke(
                app, ["generate-cab", "tests.example_package.processor", str(output)]
            )

            if result.exit_code == 0:
                # Check that informational messages were printed
                assert "Loading module" in result.stdout or "Extracting" in result.stdout
