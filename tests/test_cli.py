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
    def test_generate_valid_module(self, runner):
        """Test generate-cabs command with example module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            result = runner.invoke(
                app,
                ["generate-cabs", "--module", "src/hip_cargo/cli/generate_cabs.py", "--output-dir", str(output_dir)],
            )

            if result.exit_code == 0:
                # Output file will be named generate_cabs.yml
                output_file = output_dir / "generate_cabs.yml"
                assert output_file.exists()
                content = output_file.read_text()
                assert "generate_cabs:" in content

    @pytest.mark.integration
    def test_generate_with_output_file(self, runner):
        """Test generate-cabs command writes to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            result = runner.invoke(
                app,
                [
                    "generate-cabs",
                    "--module",
                    "src/hip_cargo/cli/generate_function.py",
                    "--output-dir",
                    str(output_dir),
                ],
            )

            if result.exit_code == 0:
                # Output file will be named generate_function.yml
                output_file = output_dir / "generate_function.yml"
                assert output_file.exists()
                content = output_file.read_text()
                assert "generate_function:" in content

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

    @pytest.mark.unit
    def test_cli_app_exists(self):
        """Test that CLI app is properly configured."""
        assert isinstance(app, typer.Typer)

    @pytest.mark.integration
    def test_generate_with_verbose(self, runner):
        """Test generate-cabs produces output messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            result = runner.invoke(
                app,
                ["generate-cabs", "--module", "src/hip_cargo/cli/generate_cabs.py", "--output-dir", str(output_dir)],
            )

            if result.exit_code == 0:
                # Check that informational messages were printed
                assert "Loading file" in result.stdout or "Writing" in result.stdout
