"""Generate Python function signatures from Stimela cab definitions."""

from typing import Any, Optional

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


def extract_custom_types(dct: dict[str, Any]) -> set[str]:
    """
    Extract all custom types used in input parameters.

    Args:
        inputs: Dictionary of input parameters

    Returns:
        Set of custom type names used
    """
    custom_types = set()
    for param_def in dct.values():
        dtype = param_def.get("dtype", "str")
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


def split_info_at_periods(info: str) -> str:
    """
    Split info string at periods to create multi-line help text.

    This helps avoid long line issues in generated code.

    Args:
        info: Info string to split

    Returns:
        Info string with newlines after periods
    """
    if not info:
        return info

    # Split at ". " (period followed by space) to preserve sentence boundaries
    # This avoids splitting on periods in numbers like "1.5" or file extensions
    sentences = []
    current = ""
    i = 0

    while i < len(info):
        current += info[i]
        # Check if we hit a period followed by space (or end of string)
        if info[i] == "." and (i + 1 >= len(info) or (i + 1 < len(info) and info[i + 1] == " ")):
            # Found end of sentence
            sentence = current.strip()
            if sentence:
                sentences.append(sentence)
            current = ""
            # Skip the space after the period
            if i + 1 < len(info) and info[i + 1] == " ":
                i += 1
        i += 1

    # Add any remaining text
    remaining = current.strip()
    if remaining:
        sentences.append(remaining)

    # Join with newlines
    return "\n".join(sentences)


def generate_parameter_signature(
    param_name: str, param_def: dict[str, Any], policies: Optional[dict[str, Any]] = None
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
    py_param_name = param_name.replace("-", "_")

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
        info = info + ".\nStimela dtype: " + dtype
    else:
        # Determine Python type normally
        py_type = stimela_dtype_to_python_type(dtype, preserve_custom=True)

    # Split info at periods to avoid long lines (after all modifications)
    info = split_info_at_periods(info)

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
        # Handle boolean first (before int check, since bool is subclass of int)
        if isinstance(val, bool):
            return "True" if val else "False"
        elif val is None:
            return "None"
        elif isinstance(val, (int, float)):
            return str(val)
        elif isinstance(val, str):
            # Check if this is a numeric string and dtype is numeric
            if dtype in ["int", "float"]:
                try:
                    # Try to parse as float (handles scientific notation)
                    float_val = float(val)
                    # If dtype is int, convert to int
                    if dtype == "int":
                        return str(int(float_val))
                    else:
                        return str(float_val)
                except (ValueError, TypeError):
                    # Not a valid number, treat as string
                    pass
            # Regular string
            return f'"{val}"'
        else:
            return str(val)

    # Check if info contains newlines (needs special formatting for typer)
    has_newlines = "\n" in info

    # Build the Typer annotation (Annotated style)
    if is_positional:
        # Arguments
        parser_part = ", parser=Path" if needs_parser else ""
        if has_newlines:
            # Multi-line help - split into quoted strings
            info_lines = info.split("\n")
            info_lines_escaped = [line.replace('"', '\\"') for line in info_lines]
            # Build multi-line help string with trailing spaces for proper concatenation
            if len(info_lines_escaped) > 1:
                help_str = f'"{info_lines_escaped[0]} "'
                for line in info_lines_escaped[1:-1]:
                    help_str += f'\n                 "{line} "'
                # Last line has no trailing space
                help_str += f'\n                 "{info_lines_escaped[-1]}"'
            else:
                help_str = f'"{info_lines_escaped[0]}"'
            typer_part = f"typer.Argument({parser_part[2:] + ', ' if parser_part else ''}help={help_str})"
        else:
            # Escape quotes for single-line help
            info_escaped = info.replace('"', '\\"')
            typer_part = f'typer.Argument({parser_part[2:] + ", " if parser_part else ""}help="{info_escaped}")'

        if required:
            return f"    {py_param_name}: Annotated[{py_type}, {typer_part}],"
        else:
            # Positional with default (rare but possible)
            default_val = format_default(default)
            return f"    {py_param_name}: Annotated[{py_type}, {typer_part}] = {default_val},"
    else:
        # Options - add parser for custom types
        parser_part = "parser=Path, " if needs_parser else ""

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

            # Split info by newlines and quote each sentence
            info_lines = info.split("\n")
            # Escape quotes in each line
            info_lines_escaped = [line.replace('"', '\\"') for line in info_lines]

            # First line starts with help=
            # Add space at end of each line except the last for proper concatenation
            if len(info_lines_escaped) > 1:
                lines_out.append(f'            help="{info_lines_escaped[0]} "')
                # Subsequent lines (except last) also need trailing space
                for line in info_lines_escaped[1:-1]:
                    lines_out.append(f'                 "{line} "')
                # Last line has no trailing space
                lines_out.append(f'                 "{info_lines_escaped[-1]}"')
            else:
                lines_out.append(f'            help="{info_lines_escaped[0]}"')

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


def generate_function_body(cab_def: dict[str, Any], inputs: dict[str, Any], outputs: dict[str, Any]) -> list[str]:
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
    # Format is: module.path.function_name
    command_parts = command.split(".")
    import_path = ".".join(command_parts[:-1])
    func_name = command_parts[-1]
    # Lazy import
    lines.append("    # Lazy import the core implementation")
    lines.append(f"    from {import_path} import {func_name} as {func_name}_core")
    lines.append("")

    # Detect and convert comma-separated string parameters
    # Check dtype field for List[int] or List[float]
    comma_sep_conversions = []
    for param_name, param_def in inputs.items():
        dtype = param_def.get("dtype", "str")

        # Check if this parameter needs comma-separated conversion
        if dtype in ["List[int]", "List[float]"]:
            element_type = dtype[5:-1]  # Extract type from List[type]
            py_param_name = param_name.replace("-", "_")
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

    # Separate required (positional) and optional (keyword) parameters
    positional_params = []
    keyword_params = []

    # Add input parameters
    for param_name, param_def in inputs.items():
        py_param_name = param_name.replace("-", "_")
        is_required = param_def.get("required", False)

        # Check if this parameter was converted
        converted_name = None
        for orig_name, converted in comma_sep_conversions:
            if orig_name == py_param_name:
                converted_name = converted
                break

        param_value = converted_name if converted_name else py_param_name

        if is_required:
            # Required parameters are passed positionally (no keyword)
            positional_params.append(f"        {param_value},")
        else:
            # Optional parameters are passed as keyword arguments
            keyword_params.append(f"        {py_param_name}={param_value},")

    # Add output parameters (always as keyword arguments)
    for output_name in outputs.keys():
        py_output_name = output_name.replace("-", "_")
        keyword_params.append(f"        {py_output_name}={py_output_name},")

    # Combine: positional args first, then keyword args
    all_params = positional_params + keyword_params

    # Add parameters to lines
    lines.extend(all_params)
    lines.append("    )")

    return lines
