"""Generate Python function signatures from Stimela cab definitions."""

from typing import Any, Optional

# Custom Stimela types that need NewType declarations
CUSTOM_STIMELA_TYPES = {"File", "Directory", "MS", "URI"}


def extract_trailing_comment(text: str) -> tuple[str, str]:
    """
    Extract trailing comment from text (e.g., "  # noqa: E501").

    Args:
        text: Text that may contain a trailing comment

    Returns:
        Tuple of (text_without_comment, comment) where comment includes the "#"
        If no comment found, returns (text, "")
    """
    if not text:
        return text, ""

    # Look for "  #" pattern (double space before comment)
    if "  #" in text:
        comment_idx = text.rfind("  #")
        comment = text[comment_idx:]
        text_without = text[:comment_idx].rstrip()
        return text_without, comment

    return text, ""


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
        if info[i] == "." and (i + 1 >= len(info) or info[i + 1] == " "):
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


def format_dict_multiline(d: dict[str, Any], indent_level: int = 0) -> str:
    """
    Format a dictionary with each item on a new line and trailing commas.

    This creates ruff-compatible formatting for nested dictionaries.

    Args:
        d: Dictionary to format
        indent_level: Current indentation level (for recursion)

    Returns:
        Formatted dictionary string
    """
    if not d:
        return "{}"

    indent = "    " * indent_level
    next_indent = "    " * (indent_level + 1)

    lines = ["{"]
    for key, value in d.items():
        # Format the key
        key_str = f'"{key}"' if isinstance(key, str) else str(key)

        # Format the value
        if isinstance(value, dict):
            value_str = format_dict_multiline(value, indent_level + 1)
        elif isinstance(value, list):
            # Format list values to ensure proper literal representation
            item_strs = []
            for item in value:
                if isinstance(item, dict):
                    item_repr = format_dict_multiline(item, indent_level + 2)
                elif isinstance(item, bool):
                    item_repr = "True" if item else "False"
                elif isinstance(item, str):
                    item_repr = f'"{item}"'
                elif item is None:
                    item_repr = "None"
                else:
                    item_repr = str(item)
                item_strs.append(item_repr)
            value_str = "[" + ", ".join(item_strs) + "]"
        elif isinstance(value, bool):
            value_str = "True" if value else "False"
        elif isinstance(value, str):
            value_str = f'"{value}"'
        elif value is None:
            value_str = "None"
        else:
            value_str = str(value)

        lines.append(f"{next_indent}{key_str}: {value_str},")

    lines.append(f"{indent}}}")
    return "\n".join(lines)


def generate_parameter_signature(
    param_name: str, param_def: dict[str, Any], policies: Optional[dict[str, Any]] = None
) -> str:
    """
    Generate parameter signature for a single parameter using Annotated style.

    Args:
        param_name: Parameter name (will be sanitized)
        param_def: Parameter definition from cab
        policies: Global policies (can be overridden by param policies)

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
    choices = param_def.get("choices")

    # Check if this needs comma-separated conversion (List[int] or List[float])
    # These are passed as comma-separated strings, not actual lists
    # The dtype is preserved in the stimela metadata dict for roundtrip
    needs_comma_conversion = dtype in ["List[int]", "List[float]"]
    if needs_comma_conversion:
        py_type = "str"
    else:
        # Determine Python type normally
        py_type = stimela_dtype_to_python_type(dtype, preserve_custom=True)

    # Extract trailing comment before splitting
    info, trailing_comment = extract_trailing_comment(info)

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

    # Check if info contains newlines (for proper help text formatting)
    has_newlines = "\n" in info

    # Build the Typer annotation (Annotated style)
    # ALWAYS use multi-line format with trailing commas to ensure ruff preserves the style

    lines_out = []
    lines_out.append(f"    {py_param_name}: Annotated[")
    lines_out.append(f"        {py_type},")

    # Build typer.Option with arguments on separate lines
    if required:
        lines_out.append("        typer.Option(")
        lines_out.append("            ...,")
        if needs_parser:
            lines_out.append("            parser=Path,")
    else:
        lines_out.append("        typer.Option(")
        if needs_parser:
            lines_out.append("            parser=Path,")

    # Add help text (handle multi-line info)
    if has_newlines:
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
            # Last line has no trailing space and ends with comma, plus optional comment
            if trailing_comment:
                lines_out.append(f'                 "{info_lines_escaped[-1]}",{trailing_comment}')
            else:
                lines_out.append(f'                 "{info_lines_escaped[-1]}",')
        else:
            if trailing_comment:
                lines_out.append(f'            help="{info_lines_escaped[0]}",{trailing_comment}')
            else:
                lines_out.append(f'            help="{info_lines_escaped[0]}",')
    else:
        # Single-line help text
        info_escaped = info.replace('"', '\\"')
        if trailing_comment:
            lines_out.append(f'            help="{info_escaped}",{trailing_comment}')
        else:
            lines_out.append(f'            help="{info_escaped}",')

    lines_out.append("        ),")

    # Build stimela metadata dict for non-standard fields
    stimela_meta = {}

    # Fields that are handled by typer.Option or inferred from type hints
    handled_fields = {
        "info",  # becomes help= in typer.Option
        "dtype",  # inferred from type hint (unless overridden)
        "required",  # handled by default=... in typer.Option
        "default",  # handled by function default value
        "choices",  # handled by Literal type
    }

    # Check if dtype needs explicit override (can't be inferred from type hint alone)
    # This happens when the type hint is generic (like str or Path) but dtype is specific (like File)
    if dtype not in ["str", "int", "float", "bool"]:
        # Normalize comparison: list[X] and List[X] are equivalent (Python 3.9+)
        normalized_py_type = py_type.replace("list[", "List[")
        normalized_dtype = dtype.replace("list[", "List[")

        # Check if the actual dtype differs from what we'd infer from py_type
        if normalized_py_type != normalized_dtype and not uses_literal:
            # Need to preserve explicit dtype
            stimela_meta["dtype"] = dtype

    # Check policies - only add if they contain non-standard fields
    if "policies" in param_def:
        policies_dict = param_def["policies"]
        # Standard policies that can be inferred: positional (from required), repeat (from List)
        non_standard_policies = {k: v for k, v in policies_dict.items() if k not in ["positional", "repeat"]}
        if non_standard_policies:
            stimela_meta["policies"] = non_standard_policies

    # Add all other arbitrary fields from param_def
    for key, value in param_def.items():
        if key not in handled_fields and key != "policies":
            stimela_meta[key] = value

    # If there are stimela metadata fields, add them as a dict to Annotated
    if stimela_meta:
        # Format with multi-line style and trailing commas for ruff compatibility
        stimela_dict_str = format_dict_multiline({"stimela": stimela_meta}, indent_level=2)
        lines_out.append(f"        {stimela_dict_str},")

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


def generate_function_body(cab_def: dict[str, Any], inputs: dict[str, Any], outputs: dict[str, Any]) -> list[str]:
    """
    Generate the function body with lazy import and core function call.

    When the cab definition includes an image, the body is wrapped in a try/except
    ImportError block with a container fallback. Otherwise, the existing direct
    lazy import pattern is used.

    Args:
        cab_def: Cab definition dictionary
        inputs: Input parameters dictionary
        outputs: Output parameters dictionary (non-implicit only)

    Returns:
        List of code lines for the function body
    """
    has_image = bool(cab_def.get("image"))
    # Indentation: extra two levels inside the if/try block when image is present
    indent = "            " if has_image else "    "

    lines = []
    func_name = cab_def.get("_name", "").replace("-", "_")

    if has_image:
        lines.append("    if backend == 'native' or backend == 'auto':")
        lines.append("        try:")

    # Parse the command to get the import path
    command = cab_def.get("command", "")
    # Format is: module.path.function_name
    command_parts = command.split(".")
    import_path = ".".join(command_parts[:-1])
    core_func_name = command_parts[-1]
    # Lazy import
    lines.append(f"{indent}# Lazy import the core implementation")
    lines.append(f"{indent}from {import_path} import {core_func_name} as {core_func_name}_core  # noqa: E402")
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
            lines.append(f"{indent}# Parse {py_param_name} if provided as comma-separated string")
            lines.append(f"{indent}{var_name} = None")
            lines.append(f"{indent}if {py_param_name} is not None:")
            lines.append(f'{indent}    {var_name} = [{element_type}(x.strip()) for x in {py_param_name}.split(",")]')
            lines.append("")

            comma_sep_conversions.append((py_param_name, var_name))

    # Generate the function call
    lines.append(f"{indent}# Call the core function with all parameters")
    lines.append(f"{indent}{core_func_name}_core(")

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
            positional_params.append(f"{indent}    {param_value},")
        else:
            keyword_params.append(f"{indent}    {py_param_name}={param_value},")

    # Add output parameters (positional if they have positional policy, otherwise keyword)
    for output_name, output_def in outputs.items():
        py_output_name = output_name.replace("-", "_")
        policies = output_def.get("policies", {})
        is_positional = policies.get("positional", False)

        if is_positional:
            positional_params.append(f"{indent}    {py_output_name},")
        else:
            keyword_params.append(f"{indent}    {py_output_name}={py_output_name},")

    # Combine: positional args first, then keyword args
    all_params = positional_params + keyword_params
    lines.extend(all_params)
    lines.append(f"{indent})")

    if has_image:
        lines.append(f"{indent}return")
        lines.append("        except ImportError:")
        lines.append("            if backend == 'native':")
        lines.append("                raise")
        lines.append("")
        lines.append("    # Fall back to container execution")
        lines.append("    from hip_cargo.utils.runner import run_in_container  # noqa: E402")
        lines.append("")

        # Build the params dict for run_in_container (excludes backend)
        lines.append("    run_in_container(")
        lines.append(f"        {func_name},")
        lines.append("        dict(")
        for param_name in inputs:
            py_name = param_name.replace("-", "_")
            lines.append(f"            {py_name}={py_name},")
        for output_name in outputs:
            py_name = output_name.replace("-", "_")
            lines.append(f"            {py_name}={py_name},")
        lines.append("        ),")
        lines.append("        backend=backend,")
        lines.append("        always_pull_images=always_pull_images,")
        lines.append("    )")

    return lines
