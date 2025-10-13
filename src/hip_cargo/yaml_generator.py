"""Generate YAML cab definitions."""

from pathlib import Path
from typing import Any

import yaml


def generate_cab_yaml(
    cab_name: str,
    cab_info: dict[str, Any],
    inputs: dict[str, Any],
    outputs: dict[str, Any],
) -> str:
    """
    Generate YAML string for a cab definition.

    Args:
        cab_name: Name of the cab
        cab_info: Cab configuration (from extract_cab_info)
        inputs: Input schema (from extract_inputs)
        outputs: Output schema (from extract_outputs)

    Returns:
        YAML string
    """
    cab_def = {
        "cabs": {
            cab_name: {
                **cab_info,
                "inputs": inputs,
                "outputs": outputs,
            }
        }
    }

    # Use safe_dump with nice formatting
    yaml_str = yaml.safe_dump(
        cab_def,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )

    return yaml_str


def write_cab_yaml(
    yaml_content: str,
    output_path: Path,
) -> None:
    """
    Write YAML content to a file.

    Args:
        yaml_content: YAML string to write
        output_path: Path where YAML should be written
    """

    # Write the YAML file
    if output_path:
        # Create parent directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(yaml_content)
    else:  # else write to terminal
        print(yaml_content)
