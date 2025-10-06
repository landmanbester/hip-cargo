"""Generate Python function signatures from Stimela cab definitions."""

import re
from pathlib import Path
from typing import Any

import yaml


def stimela_dtype_to_python_type(dtype: str) -> str:
    """
    Convert Stimela dtype to Python type hint string.

    Args:
        dtype: Stimela dtype (e.g., 'File', 'int', 'List[str]')

    Returns:
        Python type hint as string
    """
    # Handle List types
    if dtype.startswith("List["):
        inner_type = dtype[5:-1]  # Extract inner type
        inner_py = stimela_dtype_to_python_type(inner_type)
        return f"list[{inner_py}]"

    # Map Stimela types to Python types
    type_map = {
        "str": "str",
        "int": "int",
        "float": "float",
        "bool": "bool",
        "File": "Path",
        "Directory": "Path",
        "MS": "Path",
        "URL": "str",
        "URI": "str",
    }

    return type_map.get(dtype, "str")


def sanitize_param_name(name: str) -> str:
    """
    Convert parameter name to valid Python identifier.

    Args:
        name: Parameter name (may contain hyphens)

    Returns:
        Valid Python identifier (hyphens replaced with underscores)
    """
    return name.replace("-", "_")


def sanitize_fstring_refs(text: str) -> str:
    """
    Replace hyphenated parameter names in f-string references with underscores.

    Args:
        text: String that may contain {param-name} references

    Returns:
        String with sanitized references {param_name}
    """
    # Find all {something} patterns and replace hyphens with underscores
    def replace_hyphens(match):
        return "{" + match.group(1).replace("-", "_") + "}"

    return re.sub(r'\{([^}]+)\}', replace_hyphens, text)


def extract_info_string(info: Any) -> str:
    """
    Extract info string from cab definition.

    Args:
        info: Info field (can be string or dict/list)

    Returns:
        Clean info string
    """
    if isinstance(info, str):
        return info.strip()
    elif isinstance(info, (list, dict)):
        # Sometimes info is multi-line stored as list or dict
        if isinstance(info, list):
            return " ".join(str(line).strip() for line in info)
        else:
            # Extract the actual info from dict structure
            return str(info).strip()
    else:
        return ""


def load_cab_definition(cab_file: Path) -> dict[str, Any]:
    """
    Load a Stimela cab definition from YAML file.

    Args:
        cab_file: Path to YAML cab definition

    Returns:
        Dictionary containing cab definition

    Raises:
        ValueError: If no cab definition found in file
    """
    with open(cab_file) as f:
        data = yaml.safe_load(f)

    if "cabs" not in data:
        raise ValueError(f"No 'cabs' section found in {cab_file}")

    # Get the first (and usually only) cab
    cab_name = next(iter(data["cabs"]))
    cab_def = data["cabs"][cab_name]
    cab_def["_name"] = cab_name

    return cab_def


def generate_parameter_signature(
    param_name: str,
    param_def: dict[str, Any],
) -> str:
    """
    Generate parameter signature for a single parameter using Annotated style.

    Args:
        param_name: Parameter name (will be sanitized)
        param_def: Parameter definition from cab

    Returns:
        Parameter signature string
    """
    # Sanitize parameter name (replace hyphens with underscores)
    py_param_name = sanitize_param_name(param_name)

    dtype = param_def.get("dtype", "str")
    info_raw = param_def.get("info", "")
    info = extract_info_string(info_raw) if info_raw else ""
    required = param_def.get("required", False)
    default = param_def.get("default")
    policies = param_def.get("policies", {})
    choices = param_def.get("choices")

    # Determine Python type
    py_type = stimela_dtype_to_python_type(dtype)

    # If there are choices, should use a literal type or we handle it in validation
    # For now, just note it in comment
    choices_comment = ""
    if choices:
        choices_str = ", ".join(f"'{c}'" if isinstance(c, str) else str(c) for c in choices)
        choices_comment = f"  # choices: [{choices_str}]"

    # Determine if positional (Argument) or option
    is_positional = policies.get("positional", False)

    # Format default value for Python code
    def format_default(val):
        if isinstance(val, str):
            return f'"{val}"'
        elif isinstance(val, bool):
            return "True" if val else "False"
        elif val is None:
            return "None"
        elif isinstance(val, (int, float)):
            return str(val)
        else:
            return str(val)

    # Escape quotes in info string
    info = info.replace('"', '\\"')

    # Build the Typer annotation (Annotated style)
    if is_positional:
        # Arguments
        if required:
            typer_part = f'typer.Argument(help="{info}")'
            return f"    {py_param_name}: Annotated[{py_type}, {typer_part}],{choices_comment}"
        else:
            # Positional with default (rare but possible)
            typer_part = f'typer.Argument(help="{info}")'
            default_val = format_default(default)
            return f"    {py_param_name}: Annotated[{py_type}, {typer_part}] = {default_val},{choices_comment}"
    else:
        # Options
        if required:
            typer_part = f'typer.Option(..., help="{info}")'
            return f"    {py_param_name}: Annotated[{py_type}, {typer_part}],{choices_comment}"
        else:
            # Optional with default - NEVER put None as first arg to typer.Option()
            # The default comes from = value after the annotation
            typer_part = f'typer.Option(help="{info}")'
            if default is not None:
                default_val = format_default(default)
                return f"    {py_param_name}: Annotated[{py_type}, {typer_part}] = {default_val},{choices_comment}"
            else:
                # No default provided, use None
                # For optional types, add | None to type
                if not py_type.startswith("Optional") and " | None" not in py_type:
                    py_type = f"{py_type} | None"
                return f"    {py_param_name}: Annotated[{py_type}, {typer_part}] = None,{choices_comment}"


def generate_function_from_cab(cab_file: Path) -> str:
    """
    Generate a complete Python function from a Stimela cab definition.

    Args:
        cab_file: Path to YAML cab definition

    Returns:
        Python function code as string
    """
    cab_def = load_cab_definition(cab_file)

    cab_name = cab_def["_name"]
    # Try to get info from top level, or construct from cab name
    raw_info = cab_def.get("info", "")
    if raw_info:
        info = extract_info_string(raw_info)
    else:
        # Generate a reasonable default from cab name
        info = cab_name.replace("_", " ").title()
    inputs = cab_def.get("inputs", {})
    outputs = cab_def.get("outputs", {})

    # Extract function name from cab name (e.g., pfb_grid -> grid)
    func_name = sanitize_param_name(cab_name)
    if "_" in func_name:
        # Take last part for function name
        func_name = func_name.split("_")[-1]

    # Start building the function
    lines = []

    # Imports
    lines.append("import typer")
    lines.append("from pathlib import Path")
    lines.append("from typing_extensions import Annotated")
    lines.append("from hip_cargo import stimela_cab, stimela_output")
    lines.append("")

    lines.append('@stimela_cab(')
    lines.append(f'    name="{cab_name}",')
    lines.append(f'    info="{info}",')
    lines.append(')')

    # Output decorators
    for output_name, output_def in outputs.items():
        # Sanitize output name
        py_output_name = sanitize_param_name(output_name)
        output_dtype = output_def.get("dtype", "File")
        output_info_raw = output_def.get("info", output_def.get("implicit", ""))
        output_info = extract_info_string(output_info_raw)
        # Sanitize f-string references
        output_info = sanitize_fstring_refs(output_info)
        output_required = output_def.get("required", False)

        lines.append('@stimela_output(')
        lines.append(f'    name="{py_output_name}",')
        lines.append(f'    dtype="{output_dtype}",')
        lines.append(f'    info="{output_info}",')
        lines.append(f'    required={output_required},')
        lines.append(')')

    # Function signature
    lines.append(f"def {func_name}(")

    # Parameters
    for param_name, param_def in inputs.items():
        param_sig = generate_parameter_signature(param_name, param_def)
        lines.append(param_sig)

    lines.append("):")

    # Docstring
    lines.append('    """')
    if info:
        lines.append(f"    {info}")
        lines.append("    ")
    lines.append("    Args:")
    for param_name, param_def in inputs.items():
        py_param_name = sanitize_param_name(param_name)
        param_info = extract_info_string(param_def.get("info", ""))
        lines.append(f"        {py_param_name}: {param_info}")
    lines.append('    """')

    # Function body placeholder
    lines.append("    # TODO: Implement function")
    lines.append("    # Lazy import heavy dependencies here")
    lines.append("    # from pfb.operators import my_function")
    lines.append("    pass")

    return "\n".join(lines)


def cab_to_function_cli(cab_file: Path, output_file: Path | None = None) -> None:
    """
    CLI function to generate Python function from cab definition.

    Args:
        cab_file: Path to YAML cab definition
        output_file: Optional output file path (prints to stdout if None)
    """
    function_code = generate_function_from_cab(cab_file)

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            f.write(function_code)
        print(f"✓ Generated function written to: {output_file}")
    else:
        print(function_code)
