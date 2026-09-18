"""Shared test fixtures and configuration."""

from pathlib import Path

import pytest
import typer
from typing_extensions import Annotated

from hip_cargo import stimela_cab, stimela_output


@pytest.fixture(scope="session")
def test_data_dir():
    """Directory containing test data files."""
    return Path(__file__).parent / "data"


@pytest.fixture
def simple_function():
    """Simple function for basic testing."""

    @stimela_cab(name="simple_test", info="Simple test function")
    @stimela_output(name="result", dtype="File", info="Test result")
    def simple_test_func(input_param: Annotated[str, typer.Argument(help="Input parameter")]):
        """Simple test function."""
        pass

    return simple_test_func


@pytest.fixture
def function_with_defaults():
    """Function with default parameter values."""

    @stimela_cab(name="defaults_test", info="Function with defaults")
    def defaults_func(
        required_arg: Annotated[str, typer.Argument(help="Required argument")],
        optional_str: Annotated[str, typer.Option(help="Optional string")] = "default",
        optional_int: Annotated[int, typer.Option(help="Optional integer")] = 42,
        optional_bool: Annotated[bool, typer.Option(help="Optional boolean")] = False,
    ):
        """Function with various default values."""
        pass

    return defaults_func


@pytest.fixture
def function_no_outputs():
    """Function without any outputs."""

    @stimela_cab(name="no_outputs", info="Function without outputs")
    def no_outputs_func(input_file: Annotated[Path, typer.Argument(help="Input file")]):
        """Function without outputs."""
        pass

    return no_outputs_func
