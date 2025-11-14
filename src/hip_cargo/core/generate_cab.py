"""Core logic for generating Stimela cab definitions from Python modules."""

from pathlib import Path

from hip_cargo.utils.introspector import (
    extract_cab_info,
    extract_inputs,
    extract_outputs,
    get_function_from_module,
)
from hip_cargo.utils.yaml_generator import generate_cab_yaml, write_cab_yaml


def generate_cab(module_path: str, output_path: str) -> None:
    """Generate a Stimela cab definition from a Python module.

    Args:
        module_path: Python module path (e.g., "package.cli.command")
        output_path: Path where the YAML cab should be written

    Raises:
        ImportError: If the module cannot be imported
        AttributeError: If the module doesn't contain a decorated function
    """
    # Import the module and find the decorated function
    func, _ = get_function_from_module(module_path)

    # Extract cab information
    cab_config = func.__stimela_cab_config__
    cab_name = cab_config["name"]

    cab_info = extract_cab_info(func)
    inputs = extract_inputs(func)
    outputs = extract_outputs(func)

    # Remove explicit outputs from inputs
    for param_name, output in outputs.items():
        if not output.get("implicit", False):
            if param_name in inputs:
                inputs.pop(param_name)

    # Generate YAML
    yaml_content = generate_cab_yaml(cab_name, cab_info, inputs, outputs)

    # Write to file
    write_cab_yaml(yaml_content, Path(output_path))
