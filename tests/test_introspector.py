"""Test the introspector module."""

from pathlib import Path

import pytest
import typer
from typing_extensions import Annotated

from hip_cargo import stimela_cab, stimela_output
from hip_cargo.introspector import (
    _parse_google_docstring,
    _python_type_to_stimela_dtype,
    extract_cab_info,
    extract_inputs,
    extract_outputs,
)


class TestDtypeInference:
    """Test dtype inference functionality."""

    @pytest.mark.unit
    def test_infer_dtype_from_type_hints(self):
        """Test dtype inference from Python type hints."""
        assert _python_type_to_stimela_dtype(str, "Some string parameter") == "str"
        assert _python_type_to_stimela_dtype(int, "Some integer parameter") == "int"
        assert _python_type_to_stimela_dtype(float, "Some float parameter") == "float"
        assert _python_type_to_stimela_dtype(bool, "Some boolean parameter") == "bool"

    @pytest.mark.unit
    def test_infer_dtype_from_help_text(self):
        """Test dtype inference from help text keywords."""
        assert _python_type_to_stimela_dtype(Path, "Input File to process") == "File"
        assert _python_type_to_stimela_dtype(Path, "Output Directory for results") == "Directory"
        assert _python_type_to_stimela_dtype(str, "Input File path") == "File"
        assert _python_type_to_stimela_dtype(str, "Working Directory") == "Directory"

    @pytest.mark.unit
    def test_infer_dtype_fallback_to_path(self):
        """Test fallback to File for Path types."""
        assert _python_type_to_stimela_dtype(Path, "Some path parameter") == "File"

    @pytest.mark.unit
    def test_infer_dtype_unknown_type(self):
        """Test handling of unknown types."""

        class CustomType:
            pass

        assert _python_type_to_stimela_dtype(CustomType, "Custom parameter") == "str"


class TestDocstringParsing:
    """Test docstring parsing functionality."""

    @pytest.mark.unit
    def test_parse_google_style_docstring(self):
        """Test parsing Google-style docstrings."""
        docstring = """
        Process data with parameters.

        Args:
            input_file: Input file to process
            threshold: Threshold value for processing
            output_dir: Directory for output files

        Returns:
            Processed data
        """

        param_docs = _parse_google_docstring(docstring)
        assert "input_file" in param_docs
        assert "threshold" in param_docs
        assert "output_dir" in param_docs
        assert param_docs["input_file"] == "Input file to process"
        assert param_docs["threshold"] == "Threshold value for processing"
        assert param_docs["output_dir"] == "Directory for output files"

    @pytest.mark.unit
    def test_parse_docstring_no_args_section(self):
        """Test parsing docstring without Args section."""
        docstring = """
        Simple function without documented parameters.

        Returns:
            Some result
        """

        param_docs = _parse_google_docstring(docstring)
        assert param_docs == {}

    @pytest.mark.unit
    def test_parse_empty_docstring(self):
        """Test parsing empty or None docstring."""
        assert _parse_google_docstring("") == {}
        assert _parse_google_docstring("   ") == {}


class TestParameterExtraction:
    """Test parameter extraction from functions."""

    @pytest.fixture
    def complex_function(self):
        """Complex function with various parameter types."""

        @stimela_cab(name="complex_processor", info="Complex processing function")
        @stimela_output(name="result", dtype="File", info="Processing result")
        def complex_process(
            required_file: Annotated[Path, typer.Argument(help="Required input file")],
            optional_file: Annotated[Path, typer.Option(help="Optional input file")] = None,
            threshold: Annotated[float, typer.Option(help="Processing threshold")] = 0.5,
            iterations: Annotated[int, typer.Option(help="Number of iterations")] = 10,
            verbose: Annotated[bool, typer.Option(help="Enable verbose mode")] = False,
            mode: Annotated[str, typer.Option(help="Processing mode")] = "normal",
        ):
            """
            Complex processing function.

            Args:
                required_file: Required input file for processing
                optional_file: Optional secondary input file
                threshold: Processing threshold value
                iterations: Number of processing iterations
                verbose: Enable verbose output
                mode: Processing mode selection
            """
            pass

        return complex_process

    @pytest.mark.unit
    def test_extract_inputs_complex(self, complex_function):
        """Test extracting inputs from complex function."""
        inputs = extract_inputs(complex_function)

        assert len(inputs) == 6

        # Check each parameter
        inputs_by_name = {inp["name"]: inp for inp in inputs}

        # Required file argument
        required_file = inputs_by_name["required_file"]
        assert required_file["dtype"] == "File"
        assert required_file["required"] is True
        assert "Required input file" in required_file["info"]

        # Optional file option
        optional_file = inputs_by_name["optional_file"]
        assert optional_file["dtype"] == "File"
        assert optional_file["required"] is False
        assert optional_file["default"] is None

        # Float option
        threshold = inputs_by_name["threshold"]
        assert threshold["dtype"] == "float"
        assert threshold["default"] == 0.5

        # Integer option
        iterations = inputs_by_name["iterations"]
        assert iterations["dtype"] == "int"
        assert iterations["default"] == 10

        # Boolean option
        verbose = inputs_by_name["verbose"]
        assert verbose["dtype"] == "bool"
        assert verbose["default"] is False

        # String option
        mode = inputs_by_name["mode"]
        assert mode["dtype"] == "str"
        assert mode["default"] == "normal"

    @pytest.mark.unit
    def test_extract_cab_info_with_all_fields(self, complex_function):
        """Test extracting complete cab info."""
        cab_info = extract_cab_info(complex_function)

        assert cab_info["name"] == "complex_processor"
        assert cab_info["info"] == "Complex processing function"

    @pytest.mark.unit
    def test_extract_outputs_single(self, complex_function):
        """Test extracting single output."""
        outputs = extract_outputs(complex_function)

        assert len(outputs) == 1
        output = outputs[0]
        assert output["name"] == "result"
        assert output["dtype"] == "File"
        assert output["info"] == "Processing result"


class TestErrorHandling:
    """Test error handling in introspection."""

    @pytest.mark.unit
    def test_extract_cab_info_no_decorator(self):
        """Test extracting cab info from function without decorator."""

        def undecorated_function():
            pass

        with pytest.raises(AttributeError):
            extract_cab_info(undecorated_function)

    @pytest.mark.unit
    def test_extract_outputs_no_decorator(self):
        """Test extracting outputs from function without decorator."""

        def undecorated_function():
            pass

        outputs = extract_outputs(undecorated_function)
        assert outputs == []

    @pytest.mark.unit
    def test_extract_inputs_no_parameters(self):
        """Test extracting inputs from function with no parameters."""

        @stimela_cab(name="no_params", info="Function with no parameters")
        def no_param_function():
            pass

        inputs = extract_inputs(no_param_function)
        assert inputs == []
