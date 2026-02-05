"""Function introspection for extracting cab information."""

import ast
import re
from pathlib import Path
from typing import Any, NewType

import libcst as cst
from libcst import matchers

MS = NewType("MS", Path)
Directory = NewType("Directory", Path)
File = NewType("File", Path)
URI = NewType("URI", Path)


def unwrap_optional_libcst(annotation_node: cst.CSTNode) -> cst.CSTNode:
    """
    Unwrap Optional[...] or Union[..., None] wrappers from annotation.

    Args:
        annotation_node: The type annotation CST node

    Returns:
        The inner type if wrapped in Optional/Union, or the original node if not
    """
    if not isinstance(annotation_node, cst.Subscript):
        return annotation_node

    # Check if it's Optional or Union
    base_name = None
    if isinstance(annotation_node.value, cst.Name):
        base_name = annotation_node.value.value
    elif isinstance(annotation_node.value, cst.Attribute):
        base_name = annotation_node.value.attr.value

    if base_name in ("Optional", "Union"):
        # Extract the first non-None type
        # For Union[X, None] or Optional[X], return X
        slice_items = annotation_node.slice
        # LibCST may represent the slice as a single element, a tuple, or a list
        if isinstance(slice_items, tuple):
            slice_items = list(slice_items)
        elif not isinstance(slice_items, list):
            slice_items = [slice_items]

        for element in slice_items:
            node = element.slice.value
            # Skip None
            if isinstance(node, cst.Name) and node.value == "None":
                continue
            return node

    return annotation_node


def parse_annotated_libcst(annotation_node: cst.CSTNode) -> tuple[cst.CSTNode, list[cst.CSTNode]]:
    """
    Parse an Annotated[dtype, metadata, ...] type annotation from LibCST.

    Args:
        annotation_node: The type annotation CST node

    Returns:
        Tuple of (dtype_node, metadata_nodes) where metadata_nodes is a list
        of all metadata items (slice elements from index 1 onwards)

    Raises:
        ValueError: If not a valid Annotated type
    """
    # Handle Optional[Annotated[...]] wrapper
    unwrapped_node = unwrap_optional_libcst(annotation_node)

    # Check if it's a Subscript node (e.g., Annotated[...])
    if not isinstance(unwrapped_node, cst.Subscript):
        raise ValueError("Expected Annotated subscript type")

    # Check if base is "Annotated"
    if not (isinstance(unwrapped_node.value, cst.Name) and unwrapped_node.value.value == "Annotated"):
        raise ValueError("Expected Annotated type")

    # Extract slice elements [dtype, metadata1, metadata2, ...]
    # LibCST represents subscripts as a tuple or list of SubscriptElement
    slice_elements = unwrapped_node.slice

    # Convert to list if it's a tuple
    if isinstance(slice_elements, tuple):
        slice_elements = list(slice_elements)
    elif not isinstance(slice_elements, list):
        # Single element case - convert to list
        slice_elements = [slice_elements]

    if len(slice_elements) < 2:
        raise ValueError("Annotated requires at least 2 arguments")

    # Get dtype (first arg) and all metadata items (remaining args)
    # Each SubscriptElement has a .slice which is an Index with a .value
    dtype_node = slice_elements[0].slice.value
    metadata_nodes = [elem.slice.value for elem in slice_elements[1:]]

    return dtype_node, metadata_nodes


def extract_typer_metadata_libcst(metadata_nodes: list[cst.CSTNode]) -> dict[str, Any]:
    """
    Extract metadata from typer.Option(...) or typer.Argument(...) call.

    Searches through metadata items to find a typer call and extracts its arguments.

    Args:
        metadata_nodes: List of metadata CST nodes from Annotated

    Returns:
        Dict with keys from the typer call (help, default, etc.)

    Raises:
        ValueError: If no typer call found
    """
    # Find the typer.Option or typer.Argument call
    typer_call = None
    for node in metadata_nodes:
        if isinstance(node, cst.Call):
            # Check if it's a typer call (typer.Option, typer.Argument, etc.)
            func = node.func
            if isinstance(func, cst.Attribute):
                # typer.Option or typer.Argument
                if isinstance(func.value, cst.Name) and func.value.value == "typer":
                    typer_call = node
                    break
            elif isinstance(func, cst.Name):
                # Direct call like Option(...) - assume it's from typer
                typer_call = node
                break

    if typer_call is None:
        raise ValueError("No typer.Option() or typer.Argument() call found in metadata")

    # Extract both positional and keyword arguments using get_cst_value
    metadata = {}

    # First positional argument is typically the default value
    positional_args = [arg for arg in typer_call.args if arg.keyword is None]
    if positional_args:
        # Use get_cst_value to handle Ellipsis, None, literals, etc.
        metadata["default"] = get_cst_value(positional_args[0].value)

    # Extract keyword arguments
    for arg in typer_call.args:
        if arg.keyword is not None:
            key = arg.keyword.value
            # Use get_cst_value to handle complex values (lists, dicts, etc.)
            value = get_cst_value(arg.value)
            metadata[key] = value

    return metadata


def extract_input_libcst(param: cst.Param) -> tuple[str, dict[str, Any]]:
    """
    Extract input schema from a single function parameter LibCST node.

    Args:
        param: LibCST Param node to analyze (contains both type annotation and default)

    Returns:
        Tuple of (param_name, input_def) where input_def is a dictionary
        with input configuration (dtype, info, required, default, policies)
    """
    param_name = param.name.value

    # Get type annotation
    if param.annotation is not None:
        annotation_node = param.annotation.annotation

        # Parse Annotated[dtype, metadata, ...] directly - NO EVAL!
        try:
            dtype_node, metadata_nodes = parse_annotated_libcst(annotation_node)
        except ValueError:
            raise ValueError("Only Annotated types are supported")

        # Convert dtype to string representation
        dtype_str = _cst_node_to_code(dtype_node)

        # Extract typer metadata from the metadata items
        typer_metadata = extract_typer_metadata_libcst(metadata_nodes)
    else:
        dtype_str = "str"
        typer_metadata = {}

    # Get parameter description from typer metadata
    param_info = typer_metadata.get("help")

    # Extract inline comments from help string
    inline_comment = _extract_inline_comment_from_help_string(param)

    # Build input definition
    input_def = {}

    # Only add info field if it has a value (stimela doesn't support null)
    if param_info:
        # Append inline comment to info if found
        if inline_comment:
            input_def["info"] = f"{param_info}  {inline_comment}"
        else:
            input_def["info"] = param_info

    # dtype_str is already a string representation, no need to convert
    # Just normalize it using _dtype_to_str (handles Union, Literal, etc.)
    dtype = _dtype_to_str_from_string(dtype_str)

    if dtype != "str" and dtype != "NoneType":
        # if it's a Literal we add a choices field and assume param dtype is str
        if "Literal" in dtype:
            input_def["choices"] = ast.literal_eval(dtype.removeprefix("Literal").strip())
        else:
            input_def["dtype"] = dtype

    # Get default value from param.default
    if param.default is not None:
        # Use get_cst_value to extract default (handles None, literals, etc.)
        default = get_cst_value(param.default)
    elif "default" in typer_metadata:
        # Get default from typer.Option(default=...)
        default = typer_metadata["default"]
    else:
        raise RuntimeError(
            f"Unexpected state in input definition for parameter '{param_name}': "
            f"param.default is None and typer_metadata has no 'default' attribute. "
            f"param.default={param.default!r}, typer_metadata={typer_metadata!r}"
        )

    # Determine if required
    required = default is ...

    # Add required field if True
    if required:
        input_def["required"] = True
        input_def["policies"] = {}
        input_def["policies"]["positional"] = True
        if dtype == "list" or dtype == "List":
            input_def["policies"]["repeat"] = "list"
    else:
        # only set default if not required
        if default is not None:
            input_def["default"] = default
        if dtype == "list" or dtype == "List":
            input_def["policies"] = {}
            input_def["policies"]["repeat"] = "list"

    return param_name, input_def


def _dtype_to_str_from_string(dtype_str: str) -> str:
    """
    Normalize a dtype string representation for stimela compatibility.

    Handles string-based dtype normalization without runtime type objects.

    Args:
        dtype_str: String representation of the type (e.g., "File", "str | None", "list[File]")

    Returns:
        Normalized dtype string (e.g., "List[File]")
    """
    # Strip whitespace
    dtype_str = dtype_str.strip()

    # Remove " | None" or "| None" from Union types
    dtype_str = dtype_str.replace(" | None", "").replace("| None", "")

    # If it's just "None", return "NoneType"
    if dtype_str == "None":
        return "NoneType"

    # Handle empty string after stripping None
    if not dtype_str:
        return "str"

    # Map lowercase built-in types to stimela-compatible names
    # Handle both simple types (list) and generic types (list[File])
    type_mapping = {
        "list": "List",
        "dict": "Dict",
        "set": "Set",
        "tuple": "Tuple",
    }

    # Check for generic types like list[File], dict[str, int], etc.
    for old, new in type_mapping.items():
        # Replace "list[" with "List[" (preserve brackets and contents)
        if dtype_str.startswith(f"{old}["):
            dtype_str = f"{new}{dtype_str[len(old) :]}"
            return dtype_str
        # Simple type without brackets
        elif dtype_str == old:
            return new

    # Return as-is for custom types like File, Directory, etc.
    return dtype_str


def get_cst_value(node: cst.CSTNode) -> Any:
    """
    Extract the Python value directly from a LibCST node.

    Returns the actual Python object (int, str, list, dict, etc.)
    without round-tripping through code strings.

    Args:
        node: LibCST node to extract value from

    Returns:
        The Python value represented by the node
    """
    # Ellipsis (...)
    if isinstance(node, cst.Ellipsis):
        return ...

    # Primitives
    if isinstance(node, cst.Integer):
        return int(node.value)
    elif isinstance(node, cst.Float):
        return float(node.value)

    # Strings (handles both simple and concatenated automatically)
    elif isinstance(node, (cst.SimpleString, cst.ConcatenatedString)):
        return node.evaluated_value

    # Booleans and None (represented as Name nodes)
    elif isinstance(node, cst.Name):
        if node.value == "True":
            return True
        elif node.value == "False":
            return False
        elif node.value == "None":
            return None
        else:
            # Unknown name, return as string
            return node.value

    # Collections - recursive
    elif isinstance(node, cst.List):
        return [get_cst_value(el.value) for el in node.elements]

    elif isinstance(node, cst.Dict):
        result = {}
        for element in node.elements:
            if isinstance(element, cst.DictElement):
                key = get_cst_value(element.key)
                value = get_cst_value(element.value)
                result[key] = value
        return result

    elif isinstance(node, cst.Tuple):
        return tuple(get_cst_value(el.value) for el in node.elements)

    # For complex expressions we can't evaluate, return code representation
    else:
        return cst.Module([]).code_for_node(node).strip()


def _cst_node_to_code(node: cst.CSTNode) -> str:
    """
    Convert a CST node to its code string representation using LibCST's native unparsing.

    Args:
        node: LibCST node to convert

    Returns:
        String representation of the node's code
    """
    return cst.Module([]).code_for_node(node).strip()


def _extract_inline_comment_from_help_string(param: cst.Param) -> str | None:
    """
    Extract inline comments from help string in typer.Option() call.

    The typer.Option() call is in the annotation (Annotated[type, typer.Option(...)]),
    not in param.default.

    Args:
        param: LibCST Param node to analyze

    Returns:
        Inline comment string (including # prefix) if found, None otherwise
    """
    if param.annotation is None:
        return None

    annotation = param.annotation.annotation

    # annotation should be Annotated[...]
    if not isinstance(annotation, cst.Subscript):
        return None

    # Check if it's Annotated
    if not (isinstance(annotation.value, cst.Name) and annotation.value.value == "Annotated"):
        return None

    # Get the subscript elements (should be a tuple with at least 2 elements)
    slice_elements = annotation.slice
    if not isinstance(slice_elements, (list, tuple)) or len(slice_elements) < 2:
        return None

    # The second element should be typer.Option(...)
    second_element = slice_elements[1]
    if not isinstance(second_element.slice, cst.Index):
        return None

    option_call = second_element.slice.value
    if not isinstance(option_call, cst.Call):
        return None

    # Find the help keyword argument
    for arg in option_call.args:
        if arg.keyword is not None and arg.keyword.value == "help":
            # Check whitespace_after_arg for comments
            if hasattr(arg, "whitespace_after_arg"):
                ws_after = arg.whitespace_after_arg
                # Could be ParenthesizedWhitespace
                if hasattr(ws_after, "first_line"):
                    first_line = ws_after.first_line
                    if hasattr(first_line, "comment") and first_line.comment is not None:
                        return first_line.comment.value  # Returns the full comment including #

    return None


def parse_decorator_libcst(dec: cst.Decorator) -> dict:
    """Parse a decorator node to extract name and arguments."""
    if matchers.matches(dec, cst.Decorator(decorator=matchers.Name())):
        # Simple decorator: @decorator
        decorator_name = dec.decorator.value
        return decorator_name, {"args": [], "kwargs": {}}

    elif matchers.matches(dec, cst.Decorator(decorator=matchers.Call())):
        # Decorator with arguments: @decorator(arg1, arg2, key=value)
        call = dec.decorator
        decorator_name = cst.helpers.get_full_name_for_node(call.func)

        args = []
        kwargs = {}
        for arg in call.args:
            # Check for inline comments after this argument (in the comma's whitespace)
            inline_comment = None
            if arg.comma is not None and hasattr(arg.comma, "whitespace_after"):
                ws_after = arg.comma.whitespace_after
                if hasattr(ws_after, "first_line"):
                    first_line = ws_after.first_line
                    if hasattr(first_line, "comment") and first_line.comment is not None:
                        inline_comment = first_line.comment.value

            if arg.keyword is None:
                # Positional argument - keep as code string
                args.append(_cst_node_to_code(arg.value))
            else:
                # Keyword argument - extract the Python value directly using LibCST
                value = get_cst_value(arg.value)

                # If there's an inline comment and this is an "info" or "help" field, append it
                if inline_comment and arg.keyword.value in ("info", "help"):
                    value = f"{value}  {inline_comment}"

                kwargs[arg.keyword.value] = value

        if decorator_name != "stimela_cab":
            decorator_name = kwargs.pop("name")
        return decorator_name, {"args": args, "kwargs": kwargs}

    else:
        # Complex decorator (e.g., chained attributes)
        raise ValueError("Unsupported decorator format")


def format_info_fields(yaml_str, comment_map=None):
    """
    Replace inline info strings with multi-line format.

    Args:
        yaml_str: YAML string to format
        comment_map: Optional dict mapping line keys to comments
                     (e.g., "cabs.cab_name.outputs.output-dir.info" -> "# noqa")

    Returns:
        Formatted YAML string
    """
    # Process line by line to handle wrapped content
    lines = yaml_str.split("\n")
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        match = re.match(r"^(\s*)info:\s*(.*)$", line)

        if match:
            indent = match.group(1)
            content = match.group(2)

            # Collect continuation lines (indented more than 'info:')
            cond1 = i + 1 < len(lines)
            while cond1 and lines[i + 1].startswith(indent + "  ") and not re.match(r"^\s*\w+:", lines[i + 1]):
                i += 1
                content += " " + lines[i].strip()
                cond1 = i + 1 < len(lines)

            # Strip quotes (YAML adds them for strings with special chars)
            content = content.strip().strip("'\"")

            # Extract any trailing comment from the string itself
            # PEP 8: inline comments should have at least 2 spaces before the #
            # Use regex to match 2+ spaces before # to be flexible about whitespace
            trailing_comment = None
            comment_match = re.search(r"\s{2,}#", content)
            if comment_match:
                comment_idx = comment_match.start()
                trailing_comment = content[comment_idx:].strip()
                content = content[:comment_idx].rstrip()

            # Format the collected content
            formatted_lines = content.replace(". ", ".\n").strip().split("\n")
            result.append(f"{indent}info:")
            for j, formatted_line in enumerate(formatted_lines):
                if j == len(formatted_lines) - 1 and trailing_comment:
                    # Add comment to last line as YAML comment (not string content)
                    result.append(f"{indent}  {formatted_line}  {trailing_comment}")
                else:
                    result.append(f"{indent}  {formatted_line}")
        else:
            result.append(line)

        i += 1

    return "\n".join(result)
