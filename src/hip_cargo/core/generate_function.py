"""Core logic for generating Python functions from Stimela cab definitions."""

import subprocess
import warnings
from pathlib import Path

import yaml

from hip_cargo.utils.cab_to_function import (
    extract_custom_types,
    extract_trailing_comment,
    generate_function_body,
    generate_parameter_signature,
    split_info_at_periods,
)
from hip_cargo.utils.yaml_comments import extract_yaml_comments


def generate_function(cab_file: Path, output_file: Path, config_file: Path | None = None) -> None:
    """
    Generate a Python function from a Stimela cab definition.

    Args:
        cab_file: Path to the YAML cab definition file.
        output_file: Path where the Python function should be written.
        config_file: Optional path to ruff config file to use when formatting the generated code.

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

    # Extract inline comments from YAML file
    yaml_comments = extract_yaml_comments(cab_file)

    # load cab definition
    with open(cab_file) as f:
        data = yaml.safe_load(f)

    if "cabs" not in data:
        raise ValueError(f"Invalid cab file format: missing 'cabs' key in {cab_file}")

    cab_name = next(iter(data["cabs"]))
    cab_def = data["cabs"][cab_name]
    cab_def["_name"] = cab_name
    info = cab_def.get("info", "")

    # Helper to find comment for a given text
    def find_comment_for_text(text: str) -> str:
        """Find inline comment matching the end of the given text."""
        if not text:
            return ""
        # Check if any line in yaml_comments matches the end of this text
        for content, comment in yaml_comments.items():
            if text.rstrip().endswith(content.rstrip()):
                return comment
        return ""

    # Apply comment to main info if found
    info_comment = find_comment_for_text(info)
    if info_comment:
        info = f"{info}  {info_comment}"

    policies = cab_def.get("policies", {})
    inputs = cab_def.get("inputs", {})
    outputs = cab_def.get("outputs", {})

    # Apply comments to outputs FIRST (before building explicit_outputs)
    # This ensures both decorator and parameter get the comment
    for output_name, output_def in outputs.items():
        output_info = output_def.get("info", "")
        if output_info:
            output_comment = find_comment_for_text(output_info)
            if output_comment:
                output_def["info"] = f"{output_info}  {output_comment}"

    # sanitize function name
    func_name = cab_name.replace("-", "_")

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
    if uses_literal:
        lines.append("from typing import Annotated, Literal, NewType")
    else:
        lines.append("from typing import Annotated, NewType")
    lines.append("")
    lines.append("import typer")
    lines.append("")
    lines.append("from hip_cargo.utils.decorators import stimela_cab, stimela_output")
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
        # Extract trailing comment before splitting
        info_no_comment, trailing_comment = extract_trailing_comment(info)
        info_split = split_info_at_periods(info_no_comment)
        if "\n" in info_split:
            # Multi-line info
            info_lines = info_split.split("\n")
            info_lines_escaped = [line.replace('"', '\\"') for line in info_lines]
            if len(info_lines_escaped) > 1:
                lines.append(f'    info="{info_lines_escaped[0]} "')
                for line in info_lines_escaped[1:-1]:
                    lines.append(f'         "{line} "')
                # Add comment to last line if present
                if trailing_comment:
                    lines.append(f'         "{info_lines_escaped[-1]}",{trailing_comment}')
                else:
                    lines.append(f'         "{info_lines_escaped[-1]}",')
            else:
                if trailing_comment:
                    lines.append(f'    info="{info_lines_escaped[0]}",{trailing_comment}')
                else:
                    lines.append(f'    info="{info_lines_escaped[0]}",')
        else:
            # Single line info
            info_escaped = info_split.replace('"', '\\"')
            if trailing_comment:
                lines.append(f'    info="{info_escaped}",{trailing_comment}')
            else:
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
        # Get info - already has comment applied from earlier
        output_info_raw = output_def.get("info", "")
        output_required = output_def.get("required", False)

        lines.append("@stimela_output(")
        lines.append(f'    dtype="{output_dtype}",')
        lines.append(f'    name="{output_name}",')

        # Format output info with sentence splitting
        if output_info_raw:
            # Extract trailing comment before splitting
            output_info_no_comment, output_trailing_comment = extract_trailing_comment(output_info_raw)
            output_info_split = split_info_at_periods(output_info_no_comment)
            if "\n" in output_info_split:
                # Multi-line info
                info_lines = output_info_split.split("\n")
                info_lines_escaped = [line.replace('"', '\\"') for line in info_lines]
                if len(info_lines_escaped) > 1:
                    lines.append(f'    info="{info_lines_escaped[0]} "')
                    for line in info_lines_escaped[1:-1]:
                        lines.append(f'         "{line} "')
                    # Add comment to last line if present
                    if output_trailing_comment:
                        lines.append(f'         "{info_lines_escaped[-1]}",{output_trailing_comment}')
                    else:
                        lines.append(f'         "{info_lines_escaped[-1]}",')
                else:
                    if output_trailing_comment:
                        lines.append(f'    info="{info_lines_escaped[0]}",{output_trailing_comment}')
                    else:
                        lines.append(f'    info="{info_lines_escaped[0]}",')
            else:
                # Single line info
                output_info_escaped = output_info_split.replace('"', '\\"')
                if output_trailing_comment:
                    lines.append(f'    info="{output_info_escaped}",{output_trailing_comment}')
                else:
                    lines.append(f'    info="{output_info_escaped}",')
        else:
            lines.append('    info="",')

        if output_required:
            lines.append(f"    required={output_required},")

        if output_def.get("policies", None):
            lines.append(f"    policies={output_def.get('policies')},")

        if output_def.get("implicit", None):
            lines.append(f'    implicit="{output_def.get("implicit")}",')

        if "must_exist" in output_def:
            lines.append(f"    must_exist={output_def.get('must_exist')},")

        if "mkdir" in output_def:
            lines.append(f"    mkdir={output_def.get('mkdir')},")

        if "path_policies" in output_def:
            lines.append(f"    path_policies={output_def.get('path_policies')},")

        lines.append(")")

    # Function signature
    lines.append(f"def {func_name}(")

    # Separate required and optional parameters
    # Python requires all required params before optional ones
    required_params = []
    optional_params = []

    # Process inputs and apply comments
    for param_name, param_def in inputs.items():
        # Apply comment to input info if found
        param_info = param_def.get("info", "")
        if param_info:
            param_comment = find_comment_for_text(param_info)
            if param_comment:
                param_def = param_def.copy()
                param_def["info"] = f"{param_info}  {param_comment}"

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

    # Function body - generate the implementation
    lines.extend(generate_function_body(cab_def, inputs, explicit_outputs))

    function_code = "\n".join(lines)

    # 1. Prepare the Linter command (Check + Fix)
    # Note: We use --stdin-filename to give Ruff context, and - to read/write to stdout
    check_cmd = ["ruff", "check", "--fix", "--stdin-filename", "generated.py", "-"]

    # 2. Prepare the Formatter command
    format_cmd = ["ruff", "format", "--stdin-filename", "generated.py", "-"]

    if config_file:
        check_cmd.extend(["--config", str(config_file)])
        format_cmd.extend(["--config", str(config_file)])

    try:
        # First Pass: Lint and Fix
        lint_result = subprocess.run(
            check_cmd,
            input=function_code,
            capture_output=True,
            text=True,
            check=True,
        )

        # Second Pass: Format the result of the linting
        final_result = subprocess.run(
            format_cmd,
            input=lint_result.stdout,
            capture_output=True,
            text=True,
            check=True,
        )

        formatted_code = final_result.stdout

    except subprocess.CalledProcessError as e:
        warnings.warn("Code formatting with ruff failed; using unformatted code. Error details:\n" + e.stderr)
        formatted_code = function_code  # Fallback to unformatted code

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            f.write(formatted_code)
        print(f"Generated function written to: {output_file}")
    else:
        print(formatted_code)
