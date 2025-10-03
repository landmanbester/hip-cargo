"""Test YAML generation functionality."""

import pytest
import yaml

from hip_cargo.yaml_generator import generate_cab_yaml


class TestYamlGeneration:
    """Test YAML generation functionality."""

    @pytest.fixture
    def sample_cab_info(self):
        """Sample cab info for testing."""
        return {
            "name": "test_processor",
            "info": "A test processing function",
        }

    @pytest.fixture
    def sample_inputs(self):
        """Sample inputs for testing."""
        return [
            {
                "name": "input_file",
                "dtype": "File",
                "required": True,
                "info": "Input file to process",
            },
            {
                "name": "threshold",
                "dtype": "float",
                "required": False,
                "default": 0.5,
                "info": "Processing threshold",
            },
            {
                "name": "output_dir",
                "dtype": "Directory",
                "required": False,
                "default": "./output",
                "info": "Output directory",
            },
        ]

    @pytest.fixture
    def sample_outputs(self):
        """Sample outputs for testing."""
        return [
            {
                "name": "output_file",
                "dtype": "File",
                "info": "{input_file}.processed",
                "required": True,
            },
            {
                "name": "log_file",
                "dtype": "File",
                "info": "{output_dir}/processing.log",
                "required": False,
            },
        ]

    @pytest.mark.unit
    def test_generate_basic_yaml(self, sample_cab_info, sample_inputs, sample_outputs):
        """Test basic YAML generation."""
        yaml_content = generate_cab_yaml(
            "test_processor", sample_cab_info, sample_inputs, sample_outputs
        )

        assert yaml_content is not None
        assert isinstance(yaml_content, str)

        # Parse the YAML to verify structure
        parsed = yaml.safe_load(yaml_content)
        assert parsed["name"] == "test_processor"
        assert parsed["info"] == "A test processing function"
        assert "inputs" in parsed
        assert "outputs" in parsed

    @pytest.mark.unit
    def test_yaml_inputs_structure(self, sample_cab_info, sample_inputs, sample_outputs):
        """Test YAML inputs structure."""
        yaml_content = generate_cab_yaml(
            "test_processor", sample_cab_info, sample_inputs, sample_outputs
        )
        parsed = yaml.safe_load(yaml_content)

        inputs = parsed["inputs"]
        assert len(inputs) == 3

        # Check input_file
        input_file = inputs["input_file"]
        assert input_file["dtype"] == "File"
        assert input_file["required"] is True
        assert input_file["info"] == "Input file to process"

        # Check threshold
        threshold = inputs["threshold"]
        assert threshold["dtype"] == "float"
        assert threshold["required"] is False
        assert threshold["default"] == 0.5

        # Check output_dir
        output_dir = inputs["output_dir"]
        assert output_dir["dtype"] == "Directory"
        assert output_dir["default"] == "./output"

    @pytest.mark.unit
    def test_yaml_outputs_structure(self, sample_cab_info, sample_inputs, sample_outputs):
        """Test YAML outputs structure."""
        yaml_content = generate_cab_yaml(
            "test_processor", sample_cab_info, sample_inputs, sample_outputs
        )
        parsed = yaml.safe_load(yaml_content)

        outputs = parsed["outputs"]
        assert len(outputs) == 2

        # Check output_file
        output_file = outputs["output_file"]
        assert output_file["dtype"] == "File"
        assert output_file["info"] == "{input_file}.processed"
        assert output_file["required"] is True

        # Check log_file
        log_file = outputs["log_file"]
        assert log_file["dtype"] == "File"
        assert log_file["info"] == "{output_dir}/processing.log"
        assert log_file["required"] is False

    @pytest.mark.unit
    def test_yaml_no_outputs(self, sample_cab_info, sample_inputs):
        """Test YAML generation with no outputs."""
        yaml_content = generate_cab_yaml("test_processor", sample_cab_info, sample_inputs, [])
        parsed = yaml.safe_load(yaml_content)

        assert "outputs" in parsed
        assert parsed["outputs"] == {}

    @pytest.mark.unit
    def test_yaml_no_inputs(self, sample_cab_info, sample_outputs):
        """Test YAML generation with no inputs."""
        yaml_content = generate_cab_yaml("test_processor", sample_cab_info, [], sample_outputs)
        parsed = yaml.safe_load(yaml_content)

        assert "inputs" in parsed
        assert parsed["inputs"] == {}

    @pytest.mark.unit
    def test_yaml_minimal_input(self):
        """Test YAML generation with minimal input."""
        cab_info = {"name": "minimal", "info": "Minimal test"}

        yaml_content = generate_cab_yaml("minimal", cab_info, [], [])
        parsed = yaml.safe_load(yaml_content)

        assert parsed["name"] == "minimal"
        assert parsed["info"] == "Minimal test"
        assert parsed["inputs"] == {}
        assert parsed["outputs"] == {}

    @pytest.mark.unit
    def test_yaml_preserves_order(self, sample_cab_info, sample_inputs, sample_outputs):
        """Test that YAML preserves key order."""
        yaml_content = generate_cab_yaml(
            "test_processor", sample_cab_info, sample_inputs, sample_outputs
        )

        lines = yaml_content.strip().split("\n")

        # Check that top-level keys appear in expected order
        top_level_keys = []
        for line in lines:
            if line and not line.startswith(" ") and ":" in line:
                key = line.split(":")[0].strip()
                top_level_keys.append(key)

        assert top_level_keys == ["name", "info", "inputs", "outputs"]

    @pytest.mark.unit
    def test_yaml_boolean_handling(self):
        """Test that boolean values are handled correctly."""
        cab_info = {"name": "bool_test", "info": "Boolean test"}
        inputs = [
            {
                "name": "verbose",
                "dtype": "bool",
                "required": False,
                "default": True,
                "info": "Verbose mode",
            }
        ]
        outputs = [
            {
                "name": "result",
                "dtype": "File",
                "info": "Result file",
                "required": False,
            }
        ]

        yaml_content = generate_cab_yaml("bool_test", cab_info, inputs, outputs)
        parsed = yaml.safe_load(yaml_content)

        assert parsed["inputs"]["verbose"]["default"] is True
        assert parsed["outputs"]["result"]["required"] is False

    @pytest.mark.unit
    def test_yaml_none_handling(self):
        """Test that None values are handled correctly."""
        cab_info = {"name": "none_test", "info": "None test"}
        inputs = [
            {
                "name": "optional_param",
                "dtype": "str",
                "required": False,
                "default": None,
                "info": "Optional parameter",
            }
        ]

        yaml_content = generate_cab_yaml("none_test", cab_info, inputs, [])
        parsed = yaml.safe_load(yaml_content)

        assert parsed["inputs"]["optional_param"]["default"] is None

    @pytest.mark.unit
    def test_yaml_string_escaping(self):
        """Test that special characters in strings are handled correctly."""
        cab_info = {"name": "escape_test", "info": 'Test with special chars: {}, [], "quotes"'}
        inputs = [
            {
                "name": "pattern",
                "dtype": "str",
                "required": True,
                "info": "Pattern with special chars: *, ?, [a-z]",
            }
        ]

        yaml_content = generate_cab_yaml("escape_test", cab_info, inputs, [])
        parsed = yaml.safe_load(yaml_content)

        assert "special chars" in parsed["info"]
        assert "special chars" in parsed["inputs"]["pattern"]["info"]
