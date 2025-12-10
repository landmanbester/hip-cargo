"""Test decorators and basic functionality."""

from pathlib import Path

import pytest
import typer
from typing_extensions import Annotated

from hip_cargo import stimela_cab, stimela_output


@pytest.fixture
def sample_function_annotated():
    """Sample function using annotated style."""

    @stimela_cab(name="test_processor_annotated", info="A test processing function")
    @stimela_output(name="output_file", dtype="File", info="{input_file}.processed", required=True)
    def process_annotated(
        input_file: Annotated[Path, typer.Argument(help="Input File to process")],
        threshold: Annotated[float, typer.Option(0.5, help="Threshold value")] = 0.5,
    ):
        """
        Process a data file (Annotated style).

        Args:
            input_file: Input File to process
            threshold: Threshold value for processing
        """
        pass

    return process_annotated


@pytest.fixture
def multi_output_function():
    """Sample function with multiple outputs."""

    @stimela_cab(name="multi_processor", info="A processor with multiple outputs")
    @stimela_output(name="output_file", dtype="File", info="{input_file}.processed", required=True)
    @stimela_output(name="log_file", dtype="File", info="{output_dir}/processing.log", required=False)
    def process_multi(
        input_file: Annotated[Path, typer.Argument(help="Input File containing data")],
        output_dir: Annotated[Path, typer.Option(help="Output Directory for results")] = Path("./output"),
    ):
        """
        Process with multiple outputs.

        Args:
            input_file: Input File containing data
            output_dir: Output Directory for results
        """
        pass

    return process_multi


class TestDecorators:
    """Test the decorator functionality."""

    @pytest.mark.unit
    def test_stimela_cab_decorator_adds_metadata(self, sample_function_annotated):
        """Test that @stimela_cab adds metadata to function."""
        assert hasattr(sample_function_annotated, "__stimela_cab_config__")
        assert sample_function_annotated.__stimela_cab_config__["name"] == "test_processor_annotated"
        assert sample_function_annotated.__stimela_cab_config__["info"] == "A test processing function"

    @pytest.mark.unit
    def test_stimela_output_decorator_adds_metadata(self, sample_function_annotated):
        """Test that @stimela_output adds metadata to function."""
        assert hasattr(sample_function_annotated, "__stimela_outputs__")
        assert len(sample_function_annotated.__stimela_outputs__) == 1
        output = sample_function_annotated.__stimela_outputs__[0]
        assert output["name"] == "output_file"
        assert output["dtype"] == "File"
        assert output["info"] == "{input_file}.processed"

    @pytest.mark.unit
    def test_multiple_outputs(self, multi_output_function):
        """Test function with multiple @stimela_output decorators."""
        assert len(multi_output_function.__stimela_outputs__) == 2

        output_names = [out["name"] for out in multi_output_function.__stimela_outputs__]
        assert "output_file" in output_names
        assert "log_file" in output_names

        # Check required field
        outputs_by_name = {out["name"]: out for out in multi_output_function.__stimela_outputs__}
        assert outputs_by_name["output_file"]["required"] is True
        assert outputs_by_name["log_file"]["required"] is False


if __name__ == "__main__":
    pytest.main([__file__])
