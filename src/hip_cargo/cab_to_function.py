"""Generate Python function signatures from Stimela cab definitions."""

import re
from pathlib import Path
from typing import Any, Optional

import yaml

# Custom Stimela types that need NewType declarations
CUSTOM_STIMELA_TYPES = {"File", "Directory", "MS", "URI"}


def is_custom_type(dtype: str) -> bool:
    """
    Check if a dtype is a custom Stimela type.

    Args:
        dtype: Type string to check

    Returns:
        True if it's a custom type (File, MS, Directory, URI)
    """
    # Check base type and nested types
    for custom_type in CUSTOM_STIMELA_TYPES:
        if custom_type in dtype:
            return True
    return False


def extract_custom_types_from_inputs(inputs: dict[str, Any]) -> set[str]:
    """
    Extract all custom types used in input parameters.

    Args:
        inputs: Dictionary of input parameters

    Returns:
        Set of custom type names used
    """
    custom_types = set()
    for param_def in inputs.values():
        dtype = param_def.get("dtype", "str")
        for custom_type in CUSTOM_STIMELA_TYPES:
            if custom_type in str(dtype):
                custom_types.add(custom_type)
    return custom_types


def extract_custom_types_from_outputs(outputs: dict[str, Any]) -> set[str]:
    """
    Extract all custom types used in output parameters.

    Args:
        outputs: Dictionary of output parameters

    Returns:
        Set of custom type names used
    """
    custom_types = set()
    for output_def in outputs.values():
        dtype = output_def.get("dtype", "File")
        for custom_type in CUSTOM_STIMELA_TYPES:
            if custom_type in str(dtype):
                custom_types.add(custom_type)
    return custom_types


def stimela_dtype_to_python_type(dtype: str, preserve_custom: bool = True) -> str:
    """
    Convert Stimela dtype to Python type hint string.

    Args:
        dtype: Stimela dtype (e.g., 'File', 'int', 'List[str]')
        preserve_custom: If True, keep custom types (File, MS, etc.) as-is

    Returns:
        Python type hint as string
    """
    # Handle List types - use lowercase 'list'
    if dtype.startswith("List["):
        inner_type = dtype[5:-1]  # Extract inner type
        inner_py = stimela_dtype_to_python_type(inner_type, preserve_custom)
        return f"list[{inner_py}]"

    # Handle Tuple types - use lowercase 'tuple'
    if dtype.startswith("Tuple["):
        inner_types = dtype[6:-1]  # Extract inner types
        # Split by comma and convert each type
        inner_parts = [stimela_dtype_to_python_type(t.strip(), preserve_custom) for t in inner_types.split(",")]
        return f"tuple[{', '.join(inner_parts)}]"

    # Map Stimela types to Python types
    type_map = {
        "str": "str",
        "int": "int",
        "float": "float",
        "bool": "bool",
        "URL": "str",
    }

    # For custom types, preserve them if requested
    if preserve_custom and dtype in CUSTOM_STIMELA_TYPES:
        return dtype

    # Otherwise map to Path
    if dtype in CUSTOM_STIMELA_TYPES:
        return "Path"

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

    return re.sub(r"\{([^}]+)\}", replace_hyphens, text)


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
    policies: Optional[dict[str, Any]] = None,
    is_output: bool = False,
) -> str:
    """
    Generate parameter signature for a single parameter using Annotated style.

    Args:
        param_name: Parameter name (will be sanitized)
        param_def: Parameter definition from cab
        policies: Global policies (can be overridden by param policies)
        is_output: Whether this is an output parameter

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
    param_policies = param_def.get("policies", policies)
    choices = param_def.get("choices")

    # Check if this needs comma-separated conversion (List[int] or List[float])
    needs_comma_conversion = dtype in ["List[int]", "List[float]"]
    if needs_comma_conversion:
        # These are passed as comma-separated strings, not actual lists
        py_type = "str"
        # Append metadata to help string for round-trip compatibility
        info = info + "Stimela dtype: " + dtype
    else:
        # Determine Python type normally
        py_type = stimela_dtype_to_python_type(dtype, preserve_custom=True)

    # Check if this is a custom type that needs a parser
    needs_parser = is_custom_type(dtype)

    # If there are choices, use Literal type instead
    uses_literal = False
    if choices:
        uses_literal = True
        # Format choices for Literal
        choices_formatted = ", ".join(f'"{c}"' if isinstance(c, str) else str(c) for c in choices)
        py_type = f"Literal[{choices_formatted}]"
        needs_parser = False  # Literal types don't need parser

    # Determine if positional (Argument) or option
    is_positional = param_policies.get("positional", False) if param_policies else False

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

    # Check if info contains newlines (needs special formatting for typer)
    has_newlines = "\n" in info

    # Build the Typer annotation (Annotated style)
    if is_positional:
        # Arguments
        parser_part = f", parser={dtype}" if needs_parser else ""
        if has_newlines:
            # Multi-line help - use triple quotes on separate lines
            typer_part = f'typer.Argument({parser_part[2:] if parser_part else ""}help=\n"""{info}\n""")'
        else:
            # Escape quotes for single-line help
            info_escaped = info.replace('"', '\\"')
            typer_part = f'typer.Argument({parser_part[2:] if parser_part else ""}help="{info_escaped}")'

        if required:
            return f"    {py_param_name}: Annotated[{py_type}, {typer_part}],"
        else:
            # Positional with default (rare but possible)
            default_val = format_default(default)
            return f"    {py_param_name}: Annotated[{py_type}, {typer_part}] = {default_val},"
    else:
        # Options - add parser for custom types
        parser_part = f"parser={dtype}, " if needs_parser else ""

        # Build the parameter signature differently for multi-line vs single-line
        if has_newlines:
            # Multi-line format with proper indentation
            # Build the parameter line by line
            lines_out = []
            lines_out.append(f"    {py_param_name}: Annotated[")
            lines_out.append(f"        {py_type},")

            # Build typer.Option with multi-line help
            if required:
                if parser_part:
                    lines_out.append(f"        typer.Option(..., {parser_part.rstrip(', ')},")
                else:
                    lines_out.append("        typer.Option(...,")
            else:
                if parser_part:
                    lines_out.append(f"        typer.Option({parser_part.rstrip(', ')},")
                else:
                    lines_out.append("        typer.Option(")
            lines_out.append("            help=")
            lines_out.append('"""' + info)
            lines_out.append('"""')
            lines_out.append("        ),")

            # Add closing bracket and default if applicable
            if default is not None and not required:
                default_val = format_default(default)
                lines_out.append(f"    ] = {default_val},")
            elif not required:
                # No default provided, use None for optional
                if " | None" not in py_type and not uses_literal:
                    # Need to go back and fix the type
                    lines_out[1] = f"        {py_type} | None,"
                lines_out.append("    ] = None,")
            else:
                lines_out.append("    ],")

            return "\n".join(lines_out)
        else:
            # Single-line format
            # Escape quotes for single-line help
            info_escaped = info.replace('"', '\\"')
            help_part = f'help="{info_escaped}"'

            if required:
                # Required parameters (both inputs and outputs) always use ...
                typer_part = f"typer.Option(..., {parser_part}{help_part})"
                return f"    {py_param_name}: Annotated[{py_type}, {typer_part}],"
            else:
                # Optional parameters or outputs
                typer_part = f"typer.Option({parser_part}{help_part})"
                if default is not None:
                    default_val = format_default(default)
                    return f"    {py_param_name}: Annotated[{py_type}, {typer_part}] = {default_val},"
                else:
                    # No default provided, use None
                    # For optional types, add | None to type
                    if " | None" not in py_type and not uses_literal:
                        py_type = f"{py_type} | None"
                    return f"    {py_param_name}: Annotated[{py_type}, {typer_part}] = None,"


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
    policies = cab_def.get("policies", {})
    inputs = cab_def.get("inputs", {})
    outputs = cab_def.get("outputs", {})

    # Extract function name from cab name (e.g., pfb_grid -> grid)
    func_name = sanitize_param_name(cab_name)
    if "_" in func_name:
        # Take last part for function name
        func_name = func_name.split("_")[-1]

    # Detect which custom types and features are used
    custom_types = extract_custom_types_from_inputs(inputs)
    custom_types.update(extract_custom_types_from_outputs(outputs))

    # Check if any parameters use choices (need Literal import)
    uses_literal = any(param_def.get("choices") for param_def in inputs.values())

    # Separate outputs into implicit and non-implicit
    # Non-implicit outputs need to be added to function signature
    explicit_outputs = {}
    for output_name, output_def in outputs.items():
        # If implicit field exists and is truthy (True or a string template), it's implicit
        implicit_value = output_def.get("implicit")
        is_implicit = bool(implicit_value)  # Any truthy value means implicit
        if not is_implicit:
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
    lines.append(f'    info="{info}",')
    # Format policies as dict, not string
    if policies:
        lines.append(f"    policies={policies},")
    lines.append(")")

    # Output decorators
    for output_name, output_def in outputs.items():
        # Sanitize output name
        py_output_name = sanitize_param_name(output_name)
        output_dtype = output_def.get("dtype", "File")
        # Get info - could be under 'info' or 'implicit'
        output_info_raw = output_def.get("info", "")
        if not output_info_raw:
            # Try implicit field
            implicit_val = output_def.get("implicit", "")
            if isinstance(implicit_val, str):
                output_info_raw = implicit_val
        output_info = extract_info_string(output_info_raw)
        # Sanitize f-string references
        output_info = sanitize_fstring_refs(output_info)
        output_required = output_def.get("required", False)

        lines.append("@stimela_output(")
        lines.append(f'    name="{py_output_name}",')
        lines.append(f'    dtype="{output_dtype}",')
        lines.append(f'    info="{output_info}",')
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
        param_sig = generate_parameter_signature(param_name, param_def, policies=policies, is_output=is_output)
        lines.append(param_sig)

    for param_name, param_def, is_output in optional_params:
        param_sig = generate_parameter_signature(param_name, param_def, policies=policies, is_output=is_output)
        lines.append(param_sig)

    lines.append("):")
    lines.append('    """')
    lines.append(f"    {info}")
    lines.append('    """')

    # Function body - generate the implementation
    lines.extend(_generate_function_body(cab_def, inputs, explicit_outputs))

    return "\n".join(lines)


def _generate_function_body(cab_def: dict[str, Any], inputs: dict[str, Any], outputs: dict[str, Any]) -> list[str]:
    """
    Generate the function body with lazy import and core function call.

    Args:
        cab_def: Cab definition dictionary
        inputs: Input parameters dictionary
        outputs: Output parameters dictionary (non-implicit only)

    Returns:
        List of code lines for the function body
    """
    lines = []

    # Parse the command to get the import path
    command = cab_def.get("command", "")
    # Format is: (module.path)function_name
    if command and "(" in command and ")" in command:
        import_path = command.split("(")[1].split(")")[0]
        func_name = command.split(")")[1]

        # Lazy import
        lines.append("    # Lazy import the core implementation")
        lines.append(f"    from {import_path} import {func_name} as {func_name}_core")
        lines.append("")
    else:
        # Fallback - should not happen with valid cabs
        lines.append("    # TODO: Add import statement")
        lines.append("    # from mypackage.core.module import function as function_core")
        lines.append("")
        func_name = "function"

    # Detect and convert comma-separated string parameters
    # Check dtype field for List[int] or List[float]
    comma_sep_conversions = []
    for param_name, param_def in inputs.items():
        dtype = param_def.get("dtype", "str")

        # Check if this parameter needs comma-separated conversion
        if dtype in ["List[int]", "List[float]"]:
            element_type = dtype[5:-1]  # Extract type from List[type]
            py_param_name = sanitize_param_name(param_name)
            var_name = f"{py_param_name}_list"

            # Generate conversion code
            lines.append(f"    # Parse {py_param_name} if provided as comma-separated string")
            lines.append(f"    {var_name} = None")
            lines.append(f"    if {py_param_name} is not None:")
            lines.append(f'        {var_name} = [{element_type}(x.strip()) for x in {py_param_name}.split(",")]')
            lines.append("")

            comma_sep_conversions.append((py_param_name, var_name))

    # Generate the function call
    lines.append("    # Call the core function with all parameters")
    lines.append(f"    {func_name}_core(")

    # Add all parameters
    all_params = []

    # Add input parameters
    for param_name in inputs.keys():
        py_param_name = sanitize_param_name(param_name)
        # Check if this parameter was converted
        converted_name = None
        for orig_name, converted in comma_sep_conversions:
            if orig_name == py_param_name:
                converted_name = converted
                break

        if converted_name:
            all_params.append(f"        {py_param_name}={converted_name},")
        else:
            all_params.append(f"        {py_param_name}={py_param_name},")

    # Add output parameters
    for output_name in outputs.keys():
        py_output_name = sanitize_param_name(output_name)
        all_params.append(f"        {py_output_name}={py_output_name},")

    # Add parameters to lines
    lines.extend(all_params)
    lines.append("    )")

    return lines


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
