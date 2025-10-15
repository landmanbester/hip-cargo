"""Test decorators and basic functionality."""

from pathlib import Path

import pytest
import typer
from typing_extensions import Annotated

from hip_cargo import stimela_cab, stimela_output
from hip_cargo.introspector import extract_cab_info, extract_inputs, extract_outputs
from hip_cargo.yaml_generator import generate_cab_yaml


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


class TestIntrospection:
    """Test the introspection functionality."""

    @pytest.mark.unit
    def test_extract_cab_info_annotated(self, sample_function_annotated):
        """Test extracting cab info from annotated function."""
        cab_info = extract_cab_info(sample_function_annotated)
        assert cab_info["flavour"] == "python"
        assert cab_info["info"] == "Process a data file (Annotated style)."
        assert "command" in cab_info
        assert cab_info["policies"]["pass_missing_as_none"] is True

    @pytest.mark.unit
    def test_extract_inputs_annotated(self, sample_function_annotated):
        """Test extracting inputs from annotated function."""
        inputs = extract_inputs(sample_function_annotated)

        assert len(inputs) == 2
        assert "input_file" in inputs
        assert "threshold" in inputs

        # Check annotated style parsing
        input_file = inputs["input_file"]
        assert input_file["dtype"] == "Path"
        assert input_file["required"] is True
        assert input_file["policies"]["positional"] is True

        threshold = inputs["threshold"]
        assert threshold["dtype"] == "float"
        assert threshold.get("required", False) is False
        assert threshold["default"] == 0.5

    @pytest.mark.unit
    def test_extract_outputs(self, sample_function_annotated):
        """Test extracting outputs from function."""
        outputs = extract_outputs(sample_function_annotated)

        assert len(outputs) == 1
        assert "output_file" in outputs
        output = outputs["output_file"]
        assert output["dtype"] == "File"
        assert output["info"] == "{input_file}.processed"
        assert output["required"] is True

    @pytest.mark.unit
    def test_extract_multiple_outputs(self, multi_output_function):
        """Test extracting multiple outputs."""
        outputs = extract_outputs(multi_output_function)

        assert len(outputs) == 2
        assert "output_file" in outputs
        assert "log_file" in outputs

        # Check required field
        assert outputs["output_file"]["required"] is True
        assert outputs["log_file"]["required"] is False


class TestYamlGeneration:
    """Test YAML generation functionality."""

    @pytest.mark.unit
    def test_generate_yaml_annotated(self, sample_function_annotated):
        """Test YAML generation for annotated function."""
        cab_info = extract_cab_info(sample_function_annotated)
        inputs = extract_inputs(sample_function_annotated)
        outputs = extract_outputs(sample_function_annotated)

        yaml_content = generate_cab_yaml("test_processor_annotated", cab_info, inputs, outputs)

        assert "cabs:" in yaml_content
        assert "test_processor_annotated:" in yaml_content
        assert "flavour: python" in yaml_content
        assert "inputs:" in yaml_content
        assert "outputs:" in yaml_content


class TestIntegration:
    """Integration tests for complete workflow."""

    @pytest.mark.integration
    def test_complete_workflow_annotated(self, sample_function_annotated):
        """Test complete workflow for annotated style."""
        cab_info = extract_cab_info(sample_function_annotated)
        inputs = extract_inputs(sample_function_annotated)
        outputs = extract_outputs(sample_function_annotated)

        yaml_content = generate_cab_yaml("test_processor_annotated", cab_info, inputs, outputs)

        assert yaml_content is not None
        assert len(yaml_content) > 0


if __name__ == "__main__":
    pytest.main([__file__])
