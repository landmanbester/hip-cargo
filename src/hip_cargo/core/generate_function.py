"""Core logic for generating Python functions from Stimela cab definitions."""

import subprocess
from pathlib import Path

import yaml

from hip_cargo.utils.cab_to_function import (
    extract_custom_types,
    generate_function_body,
    generate_parameter_signature,
    split_info_at_periods,
)


def generate_function(cab_file: Path, output_file: Path | None = None, config_file: Path | None = None) -> None:
    """Generate a Python function from a Stimela cab definition.

    Args:
        cab_path: Path to the YAML cab definition file
        output_path: Optional path where the Python function should be written.
                    If None, prints to stdout.

    Raises:
        FileNotFoundError: If the cab file doesn't exist
        ValueError: If the cab file is invalid
    """

    if not isinstance(cab_file, Path):
        cab_file = Path(cab_file)

    if not cab_file.exists():
        raise FileNotFoundError(f"Cab file not found: {cab_file}")
    else:
        print(f"Loading cab definition from: {cab_file}")

    # load cab definition
    with open(cab_file) as f:
        data = yaml.safe_load(f)

    cab_name = next(iter(data["cabs"]))
    cab_def = data["cabs"][cab_name]
    cab_def["_name"] = cab_name
    info = cab_def.get("info", "")

    policies = cab_def.get("policies", {})
    inputs = cab_def.get("inputs", {})
    outputs = cab_def.get("outputs", {})

    # sanitize function name
    func_name = cab_name.replace("-", "_")
    if "_" in func_name:
        # Take last part for function name
        func_name = func_name.split("_")[-1]

    custom_types = extract_custom_types(inputs)
    custom_types.update(extract_custom_types(outputs))
    uses_literal = any(param_def.get("choices") for param_def in inputs.values())

    # Separate outputs into implicit and non-implicit
    # Non-implicit outputs need to be added to function signature
    # But skip outputs that have the same sanitized name as inputs (to avoid duplicates)
    input_names_sanitized = {name.replace("-", "_") for name in inputs.keys()}
    explicit_outputs = {}
    for output_name, output_def in outputs.items():
        # If implicit field exists and is truthy (True or a string template), it's implicit
        implicit_value = output_def.get("implicit", False)
        output_name_sanitized = output_name.replace("-", "_")
        # Skip if not implicit AND doesn't conflict with input names
        if not implicit_value and output_name_sanitized not in input_names_sanitized:
            explicit_outputs[output_name] = output_def

    # Start building the function
    lines = []

    # Imports
    lines.append("from pathlib import Path")
    lines.append("from typing import Annotated, NewType")
    if uses_literal:
        lines.append("from typing import Literal")
    lines.append("")
    lines.append("from hip_cargo import stimela_cab, stimela_output")
    lines.append("import typer")
    lines.append("")

    # Add NewType declarations for custom types
    if custom_types:
        for custom_type in sorted(custom_types):  # Sort for consistent output
            lines.append(f'{custom_type} = NewType("{custom_type}", Path)')
        lines.append("")

    # Decorators
    lines.append("@stimela_cab(")
    lines.append(f'    name="{cab_name}",')

    # Format info with sentence splitting
    if info:
        info_split = split_info_at_periods(info)
        if "\n" in info_split:
            # Multi-line info
            info_lines = info_split.split("\n")
            info_lines_escaped = [line.replace('"', '\\"') for line in info_lines]
            if len(info_lines_escaped) > 1:
                lines.append(f'    info="{info_lines_escaped[0]} "')
                for line in info_lines_escaped[1:-1]:
                    lines.append(f'         "{line} "')
                lines.append(f'         "{info_lines_escaped[-1]}",')
            else:
                lines.append(f'    info="{info_lines_escaped[0]}",')
        else:
            # Single line info
            info_escaped = info_split.replace('"', '\\"')
            lines.append(f'    info="{info_escaped}",')
    else:
        lines.append('    info="",')

    # Format policies as dict, not string
    if policies:
        lines.append(f"    policies={policies},")
    lines.append(")")

    # Output decorators
    for output_name, output_def in outputs.items():
        # Sanitize output name
        output_dtype = output_def.get("dtype", "File")
        # Get info - could be under 'info' or 'implicit'
        output_info_raw = output_def.get("info", "")
        output_required = output_def.get("required", False)

        lines.append("@stimela_output(")
        lines.append(f'    name="{output_name}",')
        lines.append(f'    dtype="{output_dtype}",')

        # Format output info with sentence splitting
        if output_info_raw:
            output_info_split = split_info_at_periods(output_info_raw)
            if "\n" in output_info_split:
                # Multi-line info
                info_lines = output_info_split.split("\n")
                info_lines_escaped = [line.replace('"', '\\"') for line in info_lines]
                if len(info_lines_escaped) > 1:
                    lines.append(f'    info="{info_lines_escaped[0]} "')
                    for line in info_lines_escaped[1:-1]:
                        lines.append(f'         "{line} "')
                    lines.append(f'         "{info_lines_escaped[-1]}",')
                else:
                    lines.append(f'    info="{info_lines_escaped[0]}",')
            else:
                # Single line info
                output_info_escaped = output_info_split.replace('"', '\\"')
                lines.append(f'    info="{output_info_escaped}",')
        else:
            lines.append('    info="",')

        if output_required:
            lines.append(f"    required={output_required},")
        lines.append(")")

    # Function signature
    lines.append(f"def {func_name}(")

    # Separate required and optional parameters
    # Python requires all required params before optional ones
    required_params = []
    optional_params = []

    # Process inputs
    for param_name, param_def in inputs.items():
        if param_def.get("required", False):
            required_params.append((param_name, param_def, False))
        else:
            optional_params.append((param_name, param_def, False))

    # Process non-implicit outputs
    for output_name, output_def in explicit_outputs.items():
        if output_def.get("required", False):
            required_params.append((output_name, output_def, True))
        else:
            optional_params.append((output_name, output_def, True))

    # Add required parameters first, then optional
    for param_name, param_def, is_output in required_params:
        param_sig = generate_parameter_signature(param_name, param_def, policies=policies)
        lines.append(param_sig)

    for param_name, param_def, is_output in optional_params:
        param_sig = generate_parameter_signature(param_name, param_def, policies=policies)
        lines.append(param_sig)

    lines.append("):")

    # Format docstring with proper spacing
    if info:
        # Split info at periods for better formatting
        info_formatted = split_info_at_periods(info)
        lines.append('    """')
        # Handle multi-line info with proper indentation
        if "\n" in info_formatted:
            for line in info_formatted.split("\n"):
                lines.append(f"    {line}")
        else:
            lines.append(f"    {info_formatted}")
        lines.append('    """')
    else:
        # Empty docstring
        lines.append('    """TODO: Add description."""')

    # Function body - generate the implementation
    lines.extend(generate_function_body(cab_def, inputs, explicit_outputs))

    function_code = "\n".join(lines)

    # format generated code
    format_cmd = ["ruff", "format"]
    if config_file:
        format_cmd.extend(["--config", str(config_file)])
    format_cmd.append("-")  # Read from stdin

    try:
        formatted_code = subprocess.run(
            format_cmd,
            input=function_code,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        print("Error during code formatting:")
        print(e.stderr)
        formatted_code = function_code  # Fallback to unformatted code

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            f.write(formatted_code)
        print(f"Generated function written to: {output_file}")
    else:
        print(formatted_code)
