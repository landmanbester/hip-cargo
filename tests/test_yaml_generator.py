"""Test YAML generation functionality."""

import pytest
import yaml

from hip_cargo.utils.yaml_generator import generate_cab_yaml


class TestYamlGeneration:
    """Test YAML generation functionality."""

    @pytest.mark.unit
    def test_generate_basic_yaml(self):
        """Test basic YAML generation with dict inputs."""
        cab_info = {
            "flavour": "python",
            "command": "(test.module)func",
            "info": "Test function",
            "policies": {"pass_missing_as_none": True},
        }
        inputs = {
            "input_file": {
                "dtype": "File",
                "required": True,
                "info": "Input file",
            }
        }
        outputs = {
            "output_file": {
                "dtype": "File",
                "required": True,
                "info": "Output file",
            }
        }

        yaml_content = generate_cab_yaml("test_cab", cab_info, inputs, outputs)

        assert yaml_content is not None
        assert isinstance(yaml_content, str)

        # Parse and verify structure
        parsed = yaml.safe_load(yaml_content)
        assert "cabs" in parsed
        assert "test_cab" in parsed["cabs"]
        cab = parsed["cabs"]["test_cab"]
        assert cab["flavour"] == "python"
        assert cab["inputs"] == inputs
        assert cab["outputs"] == outputs

    @pytest.mark.unit
    def test_yaml_with_empty_inputs_outputs(self):
        """Test YAML generation with empty inputs and outputs."""
        cab_info = {
            "flavour": "python",
            "command": "(test)func",
            "info": "Test",
            "policies": {"pass_missing_as_none": True},
        }

        yaml_content = generate_cab_yaml("minimal", cab_info, {}, {})
        parsed = yaml.safe_load(yaml_content)

        cab = parsed["cabs"]["minimal"]
        assert cab["inputs"] == {}
        assert cab["outputs"] == {}
