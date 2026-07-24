"""Shared test fixtures and configuration."""

import os

# Disable Ray's automatic uv-run runtime env propagation before ray is imported.
# When the driver runs under `uv run`, Ray would otherwise package the project
# directory and re-resolve deps for workers via `uv run`, but workers spawned
# that way only get the default dependency group and lose access to ray itself.
# The local in-process Ray used in these tests shares the driver's venv, so the
# hook adds nothing and (in ray>=2.55) crashes on `working_dir=None`.
os.environ.setdefault("RAY_ENABLE_UV_RUN_RUNTIME_ENV", "0")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import typer  # noqa: E402
from typing_extensions import Annotated  # noqa: E402

from hip_cargo import stimela_cab, stimela_output  # noqa: E402


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
