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
        """Test generate command help."""
        result = runner.invoke(app, ["generate", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.stdout.lower()

    @pytest.mark.integration
    def test_generate_nonexistent_file(self, runner):
        """Test generate command with nonexistent file."""
        result = runner.invoke(app, ["generate", "nonexistent_file.py", "nonexistent_function"])
        assert result.exit_code != 0

    @pytest.mark.integration
    def test_generate_valid_module(self, runner, temp_module_file):
        """Test generate command with valid module."""
        result = runner.invoke(app, ["generate", str(temp_module_file), "process_temp"])

        # Clean up
        temp_module_file.unlink()

        assert result.exit_code == 0
        assert "name: temp_processor" in result.stdout
        assert "inputs:" in result.stdout
        assert "outputs:" in result.stdout

    @pytest.mark.integration
    def test_generate_with_output_file(self, runner, temp_module_file):
        """Test generate command with output file option."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as output_file:
            output_path = Path(output_file.name)

        try:
            result = runner.invoke(
                app,
                ["generate", str(temp_module_file), "process_temp", "--output", str(output_path)],
            )

            assert result.exit_code == 0
            assert output_path.exists()

            # Check output file content
            content = output_path.read_text()
            assert "name: temp_processor" in content
            assert "inputs:" in content
            assert "outputs:" in content

        finally:
            # Clean up
            temp_module_file.unlink()
            if output_path.exists():
                output_path.unlink()

    @pytest.mark.integration
    def test_generate_invalid_function(self, runner, temp_module_file):
        """Test generate command with invalid function name."""
        result = runner.invoke(app, ["generate", str(temp_module_file), "nonexistent_function"])

        # Clean up
        temp_module_file.unlink()

        assert result.exit_code != 0

    @pytest.mark.unit
    def test_cli_app_exists(self):
        """Test that CLI app is properly configured."""
        assert isinstance(app, typer.Typer)

    @pytest.mark.integration
    def test_generate_with_verbose(self, runner, temp_module_file):
        """Test generate command with verbose flag."""
        result = runner.invoke(
            app, ["generate", str(temp_module_file), "process_temp", "--verbose"]
        )

        # Clean up
        temp_module_file.unlink()

        assert result.exit_code == 0
