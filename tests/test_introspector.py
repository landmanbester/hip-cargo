"""Test the introspector module."""

from pathlib import Path

import pytest
import typer
from typing_extensions import Annotated

from hip_cargo import stimela_cab, stimela_output
from hip_cargo.utils.introspector import (
    _parse_google_docstring,
    extract_cab_info,
    extract_inputs,
    extract_outputs,
)


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

    @pytest.mark.unit
    def test_extract_inputs_basic(self):
        """Test extracting inputs from a simple function."""

        @stimela_cab(name="test", info="Test")
        def func(
            input_file: Annotated[Path, typer.Argument(help="Input file")],
        ):
            """Test function.

            Args:
                input_file: Input file to process
            """
            pass

        inputs = extract_inputs(func)

        assert isinstance(inputs, dict)
        assert "input_file" in inputs
        assert inputs["input_file"]["dtype"] == "Path"
        assert "policies" in inputs["input_file"]
        assert inputs["input_file"]["policies"]["positional"] is True

    @pytest.mark.unit
    def test_extract_cab_info_basic(self):
        """Test extracting cab info."""

        @stimela_cab(name="test_cab", info="Test cab")
        def func():
            """Test function."""
            pass

        cab_info = extract_cab_info(func)

        assert "flavour" in cab_info
        assert cab_info["flavour"] == "python"
        assert "command" in cab_info
        assert "policies" in cab_info

    @pytest.mark.unit
    def test_extract_outputs_basic(self):
        """Test extracting outputs."""

        @stimela_cab(name="test", info="Test")
        @stimela_output(name="result", dtype="File", info="Result file")
        def func():
            """Test function."""
            pass

        outputs = extract_outputs(func)

        assert isinstance(outputs, dict)
        assert "result" in outputs
        assert outputs["result"]["dtype"] == "File"
        assert outputs["result"]["info"] == "Result file"


class TestErrorHandling:
    """Test error handling in introspection."""

    @pytest.mark.unit
    def test_extract_cab_info_no_decorator(self):
        """Test extracting cab info from function without decorator."""

        def undecorated_function():
            pass

        with pytest.raises(ValueError, match="must be decorated"):
            extract_cab_info(undecorated_function)

    @pytest.mark.unit
    def test_extract_outputs_no_decorator(self):
        """Test extracting outputs from function without decorator."""

        def undecorated_function():
            pass

        outputs = extract_outputs(undecorated_function)
        assert outputs == {}

    @pytest.mark.unit
    def test_extract_inputs_no_parameters(self):
        """Test extracting inputs from function with no parameters."""

        @stimela_cab(name="no_params", info="Function with no parameters")
        def no_param_function():
            pass

        inputs = extract_inputs(no_param_function)
        assert inputs == {}
