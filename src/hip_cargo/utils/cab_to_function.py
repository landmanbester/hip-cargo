"""Generate Python function signatures from Stimela cab definitions."""

from typing import Any, Optional

# Custom Stimela types that need NewType declarations
CUSTOM_STIMELA_TYPES = {"File", "Directory", "MS", "URI"}

# Mapping from stimela dtype to ListType NewType name
STIMELA_DTYPE_TO_LIST_TYPE = {
    "List[int]": "ListInt",
    "List[float]": "ListFloat",
    "List[str]": "ListStr",
}

# Mapping from ListType name to parser function name
LIST_TYPE_PARSERS = {
    "ListInt": "parse_list_int",
    "ListFloat": "parse_list_float",
    "ListStr": "parse_list_str",
}

# Mapping from ListType name to stimela dtype
CUSTOM_LIST_TYPES = {
    "ListInt": "List[int]",
    "ListFloat": "List[float]",
    "ListStr": "List[str]",
}


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
    # Handle Optional types - unwrap and add | None
    if dtype.startswith("Optional[") and dtype.endswith("]"):
        inner = dtype[9:-1]
        inner_py = stimela_dtype_to_python_type(inner, preserve_custom)
        return f"{inner_py} | None"

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


def _format_value_multiline(value: Any, indent_level: int) -> str:
    """Format a single value for inclusion in multi-line dict/call output."""
    if isinstance(value, dict):
        return format_dict_multiline(value, indent_level)
    if isinstance(value, list):
        item_strs = []
        for item in value:
            if isinstance(item, dict):
                item_repr = format_dict_multiline(item, indent_level + 1)
            elif isinstance(item, bool):
                item_repr = "True" if item else "False"
            elif isinstance(item, str):
                item_repr = f'"{item}"'
            elif item is None:
                item_repr = "None"
            else:
                item_repr = str(item)
            item_strs.append(item_repr)
        return "[" + ", ".join(item_strs) + "]"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return f'"{value}"'
    if value is None:
        return "None"
    return str(value)


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
        key_str = f'"{key}"' if isinstance(key, str) else str(key)
        value_str = _format_value_multiline(value, indent_level + 1)
        lines.append(f"{next_indent}{key_str}: {value_str},")

    lines.append(f"{indent}}}")
    return "\n".join(lines)


def format_stimela_meta_call(meta: dict[str, Any], indent_level: int = 0) -> str:
    """
    Format a stimela metadata mapping as a ``StimelaMeta(...)`` call.

    Keys become keyword arguments; nested dicts stay as dict literals (they are
    re-frozen at runtime by ``StimelaMeta.__init__``). Produces ruff-compatible
    output with one kwarg per line and trailing commas.

    Args:
        meta: Mapping of stimela metadata fields.
        indent_level: Current indentation level.

    Returns:
        Formatted ``StimelaMeta(...)`` call string.
    """
    if not meta:
        return "StimelaMeta()"

    indent = "    " * indent_level
    next_indent = "    " * (indent_level + 1)

    lines = ["StimelaMeta("]
    for key, value in meta.items():
        value_str = _format_value_multiline(value, indent_level + 1)
        lines.append(f"{next_indent}{key}={value_str},")
    lines.append(f"{indent})")
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

    # Check if this is a comma-separated list type (List[int], List[float], List[str])
    # These use dedicated ListType NewTypes with parser functions
    # Unwrap Optional[...] for the lookup since Optional[List[int]] should use ListInt too
    is_optional = dtype.startswith("Optional[") and dtype.endswith("]")
    lookup_dtype = dtype[9:-1] if is_optional else dtype
    list_type_name = STIMELA_DTYPE_TO_LIST_TYPE.get(lookup_dtype)
    if list_type_name:
        py_type = f"{list_type_name} | None" if is_optional else list_type_name
        # Convert list defaults to comma-separated strings (ListType takes a string at CLI level)
        if isinstance(default, list):
            default = ",".join(str(v) for v in default)
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

    # Determine parser: list types use their own parser, custom path types
    # use parse_upath so the CLI accepts local paths or remote URIs.
    parser_str = None
    if list_type_name:
        parser_str = LIST_TYPE_PARSERS[list_type_name]
    elif needs_parser:
        parser_str = "parse_upath"

    # Build typer.Option with arguments on separate lines
    if required:
        lines_out.append("        typer.Option(")
        lines_out.append("            ...,")
        if parser_str:
            lines_out.append(f"            parser={parser_str},")
    else:
        lines_out.append("        typer.Option(")
        if parser_str:
            lines_out.append(f"            parser={parser_str},")

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

    # Add rich_help_panel if present in metadata
    param_metadata = param_def.get("metadata", {})
    rich_help_panel = param_metadata.get("rich_help_panel")
    if rich_help_panel:
        lines_out.append(f'            rich_help_panel="{rich_help_panel}",')

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
        "metadata",  # handled by rich_help_panel in typer.Option
    }

    # Check if dtype needs explicit override (can't be inferred from type hint alone)
    # This happens when the type hint is generic (like str or Path) but dtype is specific (like File)
    # Skip for ListType NewTypes — their dtype is inferred from the type name
    if dtype not in ["str", "int", "float", "bool"] and not list_type_name:
        # Normalize comparison: strip Optional/None wrappers and lowercase generics
        normalized_py_type = py_type.replace(" | None", "").replace("list[", "List[").replace("tuple[", "Tuple[")
        normalized_py_type = normalized_py_type.replace("dict[", "Dict[")
        normalized_dtype = dtype
        if normalized_dtype.startswith("Optional[") and normalized_dtype.endswith("]"):
            normalized_dtype = normalized_dtype[9:-1]
        normalized_dtype = normalized_dtype.replace("list[", "List[").replace("tuple[", "Tuple[")
        normalized_dtype = normalized_dtype.replace("dict[", "Dict[")

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

    # If there are stimela metadata fields, emit a StimelaMeta(...) call
    if stimela_meta:
        # Format with multi-line style and trailing commas for ruff compatibility
        stimela_call_str = format_stimela_meta_call(stimela_meta, indent_level=2)
        lines_out.append(f"        {stimela_call_str},")

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

    # Pre-flight must_exist for remote URIs before dispatching.
    # The preflight calls .exists() on remote UPaths, which may raise ImportError
    # if the fsspec backend is missing. When has_image is True, it must live
    # INSIDE the try/except block so the container fallback can catch that.
    if has_image:
        lines.append(f"{indent}# Pre-flight must_exist for remote URIs before dispatching.")
        lines.append(f"{indent}from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402")
        lines.append(f"{indent}preflight_remote_must_exist(")
        lines.append(f"{indent}    {func_name},")
        lines.append(f"{indent}    dict(")
        for param_name in inputs:
            py_name = param_name.replace("-", "_")
            lines.append(f"{indent}        {py_name}={py_name},")
        for output_name in outputs:
            py_name = output_name.replace("-", "_")
            lines.append(f"{indent}        {py_name}={py_name},")
        lines.append(f"{indent}    ),")
        lines.append(f"{indent})")
        lines.append("")
    else:
        lines.append("    # Pre-flight must_exist for remote URIs before dispatching.")
        lines.append("    from hip_cargo.utils.runner import preflight_remote_must_exist  # noqa: E402")
        lines.append("    preflight_remote_must_exist(")
        lines.append(f"        {func_name},")
        lines.append("        dict(")
        for param_name in inputs:
            py_name = param_name.replace("-", "_")
            lines.append(f"            {py_name}={py_name},")
        for output_name in outputs:
            py_name = output_name.replace("-", "_")
            lines.append(f"            {py_name}={py_name},")
        lines.append("        ),")
        lines.append("    )")
        lines.append("")

    # Lazy import
    lines.append(f"{indent}# Lazy import the core implementation")
    lines.append(f"{indent}from {import_path} import {core_func_name} as {core_func_name}_core  # noqa: E402")
    lines.append("")

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

        if is_required:
            positional_params.append(f"{indent}    {py_param_name},")
        else:
            keyword_params.append(f"{indent}    {py_param_name}={py_param_name},")

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
        lines.append("    # Resolve container image from installed package metadata")
        lines.append("    from hip_cargo.utils.config import get_container_image  # noqa: E402")
        lines.append("    from hip_cargo.utils.runner import run_in_container  # noqa: E402")
        lines.append("")

        # Derive distribution name from command: "pfb_imaging.core.grid.grid" → "pfb-imaging"
        command = cab_def.get("command", "")
        import_name = command.split(".")[0] if command else ""
        dist_name = import_name.replace("_", "-")

        lines.append(f'    image = get_container_image("{dist_name}")')
        lines.append("    if image is None:")
        lines.append(f'        raise RuntimeError("No Container URL in {dist_name} metadata.")')
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
        lines.append("        image=image,")
        lines.append("        backend=backend,")
        lines.append("        always_pull_images=always_pull_images,")
        lines.append("    )")

    return lines
