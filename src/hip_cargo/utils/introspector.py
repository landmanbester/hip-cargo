"""Function introspection for extracting cab information."""

import ast
import re
from pathlib import Path
from typing import Any

import libcst as cst
import yaml
from libcst import matchers

from hip_cargo.utils.spec import CommandSpec, ModuleSpec, ParamSpec
from hip_cargo.utils.types import LIST_DTYPE_PARSERS


def _normalize_list_default(dtype: str, default: Any) -> Any:
    """Coerce a comma-separated string default into a list for List dtypes.

    Stimela validates defaults against the declared dtype, so a ``ListStr``
    param with default ``"a,b,c"`` must render as ``[a, b, c]`` in the cab
    YAML rather than the raw string (issue #82). Non-list dtypes and
    already-list defaults are returned unchanged.
    """
    lookup = dtype[len("Optional[") : -1] if dtype.startswith("Optional[") and dtype.endswith("]") else dtype
    parser = LIST_DTYPE_PARSERS.get(lookup)
    if parser is None or not isinstance(default, str):
        return default
    return parser(default)


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


def _callee_name(call: cst.Call) -> str:
    """Name of the called function, e.g. ``Option`` for ``typer.Option(...)``."""
    func = call.func
    if isinstance(func, cst.Attribute):
        return func.attr.value
    if isinstance(func, cst.Name):
        return func.value
    return ""


def _find_typer_call(metadata_nodes: list[cst.CSTNode]) -> cst.Call | None:
    """Return the ``typer.Option``/``typer.Argument`` call among Annotated metadata, if any."""
    for node in metadata_nodes:
        if isinstance(node, cst.Call):
            func = node.func
            # typer.Option(...) / typer.Argument(...)
            if isinstance(func, cst.Attribute):
                if isinstance(func.value, cst.Name) and func.value.value == "typer":
                    return node
            # Direct call like Option(...) - assume it's from typer
            elif isinstance(func, cst.Name):
                return node
    return None


def _typer_default_node(metadata_nodes: list[cst.CSTNode]) -> cst.BaseExpression | None:
    """The expression a ``typer.Option`` uses as its default: ``default=`` or the first positional."""
    typer_call = _find_typer_call(metadata_nodes)
    if typer_call is None:
        return None
    for arg in typer_call.args:
        if arg.keyword is not None and arg.keyword.value == "default":
            return arg.value
    positional = [arg for arg in typer_call.args if arg.keyword is None]
    return positional[0].value if positional else None


def extract_typer_metadata_libcst(metadata_nodes: list[cst.CSTNode], param_name: str | None = None) -> dict[str, Any]:
    """
    Extract metadata from a typer.Option(...) call.

    Searches through metadata items to find a typer call and extracts its arguments.
    Constructs a cab cannot express are rejected here rather than mis-parsed: a cab
    and its CLI module are two renderings of one definition, so anything that cannot
    survive the round trip is not part of the dialect.

    Args:
        metadata_nodes: List of metadata CST nodes from Annotated
        param_name: Parameter being parsed, used to make error messages actionable

    Returns:
        Dict with keys from the typer call (help, default, etc.)

    Raises:
        ValueError: If no typer call is found, if it is a ``typer.Argument``, or if
            it carries param_decls.
    """
    typer_call = _find_typer_call(metadata_nodes)
    if typer_call is None:
        raise ValueError("No typer.Option() or typer.Argument() call found in metadata")

    where = f"Parameter '{param_name}': " if param_name else ""

    if _callee_name(typer_call) == "Argument":
        raise ValueError(
            f"{where}typer.Argument is not supported. A cab cannot express a positional "
            f"CLI argument, so the CLI module could not be regenerated from it. Declare it as "
            f"typer.Option(..., help=...) instead; the cab still records policies.positional: true."
        )

    # Extract both positional and keyword arguments using get_cst_value
    metadata = {}

    # In Annotated style every string positional is a param_decl, never a default.
    # Flag names are derived from the parameter name, so a cab has nowhere to record
    # them and the round trip would silently drop them -- reject instead (#112).
    positional_args = [arg for arg in typer_call.args if arg.keyword is None]
    decls = [value for value in (get_cst_value(arg.value) for arg in positional_args) if isinstance(value, str)]
    if decls:
        raise ValueError(
            f"{where}typer.Option param_decls are not supported ({', '.join(repr(d) for d in decls)}). "
            f"Flag names are derived from the parameter name so that a cab and its CLI module stay "
            f"in one-to-one correspondence. Remove them."
        )

    # First positional argument is the default value
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


def extract_stimela_metadata_libcst(metadata_nodes: list[cst.CSTNode]) -> dict[str, Any]:
    """
    Extract custom Stimela metadata from Annotated metadata items.

    Recognises two forms:

    * Preferred::

          Annotated[Type, typer.Option(...), StimelaMeta(key=value, ...)]

    * Legacy dict literal::

          Annotated[Type, typer.Option(...), {"stimela": {...}}]

    Args:
        metadata_nodes: List of metadata CST nodes from Annotated

    Returns:
        Dict with Stimela-specific metadata, or empty dict if not found
    """
    for node in metadata_nodes:
        # Preferred form: StimelaMeta(...) call
        if isinstance(node, cst.Call):
            if _callee_name(node) == "StimelaMeta":
                result: dict[str, Any] = {}
                for arg in node.args:
                    if arg.keyword is not None:
                        result[arg.keyword.value] = get_cst_value(arg.value)
                return result

        # Legacy form: {"stimela": {...}} dict literal
        if isinstance(node, cst.Dict):
            dict_value = get_cst_value(node)
            if isinstance(dict_value, dict) and "stimela" in dict_value:
                return dict_value["stimela"]
    return {}


def extract_param_spec(param: cst.Param) -> ParamSpec:
    """Extract a neutral :class:`ParamSpec` from a CST Param node.

    Pulls only structural facts — name, type-as-string, default, typer kwargs,
    stimela metadata, inline comment. Applies no cab semantics. Used by both
    cab and schema generators.

    Args:
        param: LibCST Param node to analyse.

    Returns:
        A :class:`ParamSpec` describing the parameter.

    Raises:
        ValueError: If the parameter has a non-``Annotated`` type annotation, uses a
            construct outside the dialect (``typer.Argument``, param_decls), or is
            required without the ``...`` marker.
    """
    param_name = param.name.value

    if param.annotation is not None:
        annotation_node = param.annotation.annotation
        try:
            dtype_node, metadata_nodes = parse_annotated_libcst(annotation_node)
        except ValueError:
            raise ValueError("Only Annotated types are supported")

        dtype_str = _cst_node_to_code(dtype_node)
        typer_metadata = extract_typer_metadata_libcst(metadata_nodes, param_name)
        stimela_metadata = extract_stimela_metadata_libcst(metadata_nodes)
        typer_default_node = _typer_default_node(metadata_nodes)
    else:
        dtype_str = "str"
        typer_metadata = {}
        stimela_metadata = {}
        typer_default_node = None

    default_node = param.default if param.default is not None else typer_default_node
    if default_node is not None and _is_numeric_dtype(dtype_str) and not _is_literal(default_node):
        raise ValueError(
            f"Parameter '{param_name}': default `{_cst_node_to_code(default_node)}` is not a literal. "
            f"The cab would carry that source text as the default of a `{dtype_str}` parameter, "
            f"which Stimela cannot use. Write the value itself (e.g. `= -1`)."
        )

    inline_comment = _extract_inline_comment_from_help_string(param)

    if param.default is not None:
        default = get_cst_value(param.default)
    elif "default" in typer_metadata:
        default = typer_metadata["default"]
    else:
        raise ValueError(
            f"Parameter '{param_name}': a required parameter must be declared as "
            f"typer.Option(..., help=...) -- the ellipsis is what marks it required. "
            f"Add it, or give the parameter a default."
        )

    return ParamSpec(
        name=param_name,
        dtype_str=dtype_str,
        default=default,
        required=default is ...,
        help=typer_metadata.get("help"),
        stimela_meta=dict(stimela_metadata),
        raw_typer_meta=dict(typer_metadata),
        inline_comment=inline_comment,
    )


def param_spec_to_cab_input(spec: ParamSpec) -> tuple[str, dict[str, Any]]:
    """Convert a :class:`ParamSpec` to a cab YAML input definition.

    All cab-specific shaping lives here: dtype inference vs explicit override,
    Literal → choices, policies (positional/repeat), info+inline-comment merge,
    rich_help_panel → metadata dict, and the final stimela_metadata merge.

    Args:
        spec: Neutral parameter specification.

    Returns:
        Tuple of ``(param_name, input_def)`` where ``input_def`` is the dict
        ready to be inserted under the cab's ``inputs`` mapping.
    """
    stimela_metadata = spec.stimela_meta
    input_def: dict[str, Any] = {}

    if spec.help:
        if spec.inline_comment:
            input_def["info"] = f"{spec.help}  {spec.inline_comment}"
        else:
            input_def["info"] = spec.help

    if "dtype" in stimela_metadata:
        dtype = stimela_metadata["dtype"]
        if dtype != "str":
            input_def["dtype"] = dtype
    else:
        dtype = _dtype_to_str_from_string(spec.dtype_str)
        if dtype != "str" and dtype != "NoneType":
            if "Literal" in dtype:
                # Literal[...] | None normalises to Optional[Literal[...]]
                is_optional = dtype.startswith("Optional[")
                literal = dtype[9:-1] if is_optional else dtype
                choices = ast.literal_eval(literal.removeprefix("Literal").strip())
                input_def["choices"] = choices
                # With a None default, nullability is implied by the input being neither
                # required nor defaulted. Otherwise it must be carried by the dtype.
                if is_optional and spec.default is not None and spec.default is not ...:
                    choice_types = {type(c).__name__ for c in choices}
                    elem = choice_types.pop() if len(choice_types) == 1 else "str"
                    input_def["dtype"] = f"Optional[{elem}]"
            else:
                input_def["dtype"] = dtype

    if spec.required:
        input_def["required"] = True
        input_def["policies"] = {}
        input_def["policies"]["positional"] = True
        if dtype == "list" or dtype == "List":
            input_def["policies"]["repeat"] = "list"
    else:
        if spec.default is not None:
            input_def["default"] = _normalize_list_default(dtype, spec.default)
        if dtype == "list" or dtype == "List":
            input_def["policies"] = {}
            input_def["policies"]["repeat"] = "list"

    rich_help_panel = spec.raw_typer_meta.get("rich_help_panel")
    if rich_help_panel:
        input_def.setdefault("metadata", {})["rich_help_panel"] = rich_help_panel

    for key, value in stimela_metadata.items():
        if key == "dtype":
            continue
        elif key == "policies" and "policies" in input_def:
            input_def["policies"].update(value)
        elif key == "metadata" and "metadata" in input_def:
            # Merge with rich_help_panel (and any future typer-derived metadata)
            # rather than overwriting.
            input_def["metadata"].update(value)
        else:
            input_def[key] = value

    return spec.name, input_def


def _strip_top_level_none(dtype_str: str) -> tuple[str, bool]:
    """Remove ``None`` members from a top-level ``X | None`` union.

    Parsed structurally so ``None`` inside subscripts (e.g. ``Literal["a | None"]``)
    is left untouched and spacing around ``|`` does not matter.

    Args:
        dtype_str: Source text of a type annotation.

    Returns:
        Tuple of ``(remaining_type_str, is_optional)``. A bare ``None`` returns ``("None", False)``.
    """
    try:
        node = cst.parse_expression(dtype_str)
    except cst.ParserSyntaxError:
        return dtype_str, False

    def union_members(n: cst.BaseExpression) -> list[cst.BaseExpression]:
        if isinstance(n, cst.BinaryOperation) and isinstance(n.operator, cst.BitOr):
            return union_members(n.left) + union_members(n.right)
        return [n]

    members = union_members(node)
    kept = [m for m in members if not (isinstance(m, cst.Name) and m.value == "None")]
    if len(kept) == len(members) or not kept:
        return dtype_str, False
    return " | ".join(_cst_node_to_code(m) for m in kept), True


def _dtype_to_str_from_string(dtype_str: str) -> str:
    """
    Normalize a dtype string representation for stimela compatibility.

    Handles string-based dtype normalization without runtime type objects.

    Args:
        dtype_str: String representation of the type (e.g., "File", "str | None", "list[File]")

    Returns:
        Normalized dtype string (e.g., "List[File]")
    """
    dtype_str, is_optional = _strip_top_level_none(dtype_str.strip())

    # If it's just "None", return "NoneType"
    if dtype_str == "None":
        return "NoneType"

    # Handle empty string after stripping None
    if not dtype_str:
        return "str"

    # Map custom list NewTypes to their stimela dtypes
    list_type_mapping = {
        "ListInt": "List[int]",
        "ListFloat": "List[float]",
        "ListStr": "List[str]",
    }
    if dtype_str in list_type_mapping:
        resolved = list_type_mapping[dtype_str]
        return f"Optional[{resolved}]" if is_optional else resolved

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
            resolved = f"{new}{dtype_str[len(old) :]}"
            return f"Optional[{resolved}]" if is_optional else resolved
        # Simple type without brackets
        elif dtype_str == old:
            return f"Optional[{new}]" if is_optional else new

    # Return as-is for custom types like File, Directory, etc.
    return f"Optional[{dtype_str}]" if is_optional else dtype_str


_NUMERIC_DTYPES = frozenset({"int", "float", "bool"})


def _is_numeric_dtype(dtype_str: str) -> bool:
    """True for ``int``/``float``/``bool``, optionally made optional (``| None``, ``Optional[...]``)."""
    names = set(re.findall(r"[A-Za-z_]\w*", dtype_str)) - {"None", "Optional", "Union"}
    return bool(names) and names <= _NUMERIC_DTYPES


def _is_literal(node: cst.CSTNode) -> bool:
    """True if :func:`get_cst_value` evaluates ``node`` rather than falling back to its source text."""
    if isinstance(node, (cst.Ellipsis, cst.Integer, cst.Float, cst.SimpleString, cst.ConcatenatedString)):
        return True
    if isinstance(node, cst.Name):
        return node.value in {"True", "False", "None"}
    if isinstance(node, (cst.List, cst.Tuple)):
        return all(_is_literal(el.value) for el in node.elements)
    if isinstance(node, cst.Dict):
        return all(
            isinstance(el, cst.DictElement) and _is_literal(el.key) and _is_literal(el.value) for el in node.elements
        )
    if isinstance(node, cst.UnaryOperation):
        if isinstance(node.operator, cst.BitInvert):
            return isinstance(node.expression, cst.Integer)
        return isinstance(node.operator, (cst.Minus, cst.Plus)) and isinstance(
            node.expression, (cst.Integer, cst.Float)
        )
    return False


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

    # Signed numeric literals: -1 parses as UnaryOperation(Minus, Integer("1")),
    # not as a negative Integer. Without this the fallback below would stringify
    # it and emit `default: '-1'` under a numeric dtype.
    elif isinstance(node, cst.UnaryOperation):
        operand = get_cst_value(node.expression)
        if isinstance(operand, bool) or not isinstance(operand, (int, float, complex)):
            return cst.Module([]).code_for_node(node).strip()
        if isinstance(node.operator, cst.Minus):
            return -operand
        elif isinstance(node.operator, cst.Plus):
            return +operand
        elif isinstance(node.operator, cst.BitInvert) and isinstance(operand, int):
            return ~operand
        return cst.Module([]).code_for_node(node).strip()

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

                # If there's an inline comment and this is an "info", "help", or "implicit" field, append it
                if inline_comment and arg.keyword.value in ("info", "help", "implicit"):
                    value = f"{value}  {inline_comment}"

                kwargs[arg.keyword.value] = value

        if decorator_name != "stimela_cab":
            decorator_name = kwargs.pop("name")
        return decorator_name, {"args": args, "kwargs": kwargs}

    else:
        # Complex decorator (e.g., chained attributes)
        raise ValueError("Unsupported decorator format")


def parse_module(module_path: Path) -> ModuleSpec:
    """Parse one CLI module and return all ``@stimela_cab`` commands as a :class:`ModuleSpec`.

    A single CST walk extracts every ``@stimela_cab``-decorated function,
    its decorators, and its parameters. Both ``generate-cabs`` and
    ``generate-schemas`` consume this IR.

    Args:
        module_path: Path to the ``.py`` CLI module.

    Returns:
        A :class:`ModuleSpec` containing zero or more :class:`CommandSpec`
        entries (zero if the module has no ``@stimela_cab`` decorators).
    """
    module_path = Path(module_path)
    with open(module_path, "r") as f:
        tree = cst.parse_module(f.read())

    commands: list[CommandSpec] = []
    for node in tree.body:
        if not isinstance(node, cst.FunctionDef):
            continue

        decorators: dict[str, dict[str, Any]] = {}
        for dec in node.decorators:
            deco_name, deco_args = parse_decorator_libcst(dec)
            decorators[deco_name] = deco_args

        if "stimela_cab" not in decorators:
            continue

        params = tuple(extract_param_spec(p) for p in node.params.params)
        commands.append(
            CommandSpec(
                name=node.name.value,
                module_path=module_path,
                decorators=decorators,
                params=params,
            )
        )

    return ModuleSpec(path=module_path, commands=tuple(commands))


_INFO_FIELD = re.compile(r"^(\s*)(info|implicit):\s*(.*)$")


def _loads_as(block: list[str], indent: str, field_name: str, value: str) -> bool:
    """True if ``block`` (lines at ``indent``) loads as ``{field_name: value}``."""
    try:
        loaded = yaml.safe_load("\n".join(line[len(indent) :] for line in block))
    except yaml.YAMLError:
        return False
    return loaded == {field_name: value}


def _info_candidates(indent: str, content: str, comment: str | None) -> list[list[str]]:
    """Multi-line renderings of an info value, most readable first.

    One sentence per line, plain; then the same lines as one single-quoted
    scalar (a multi-line single-quoted scalar folds to the same string). The
    comment goes after the last line, outside the scalar.
    """
    sentences = content.replace(". ", ".\n").strip().split("\n")
    quoted = [line.replace("'", "''") for line in sentences]
    quoted[0] = "'" + quoted[0]
    quoted[-1] = quoted[-1] + "'"
    suffix = f"  {comment}" if comment else ""
    return [
        [f"{indent}info:"] + [f"{indent}  {line}" for line in lines[:-1]] + [f"{indent}  {lines[-1]}{suffix}"]
        for lines in (sentences, quoted)
    ]


def _single_line(indent: str, field_name: str, content: str, comment: str | None) -> list[str]:
    """``field: <scalar>`` quoted however YAML needs it (several lines if the value has newlines)."""
    dumped = yaml.safe_dump({field_name: content}, allow_unicode=True, width=_YAML_WIDTH).rstrip("\n").split("\n")
    rendered = [f"{indent}{line}" if line else "" for line in dumped]
    if comment:
        rendered[-1] += f"  {comment}"
    return rendered


_YAML_WIDTH = 10000


def format_info_fields(yaml_str: str) -> str:
    """
    Rewrite dumped ``info``/``implicit`` scalars into their cab form.

    ``info`` goes one sentence per line; ``implicit`` stays on one line. Both
    move an inline comment carried in the string (``\\s{2,}#``) out of the
    scalar and into a YAML comment.

    Each value is first decoded by YAML itself (so quoting and escapes from
    ``safe_dump`` are undone exactly), and every rewrite is reloaded and checked
    against that value. A rendering that would load as something else -- a
    mapping, a comment, a sequence -- is not used; the value falls back to a
    single line quoted by ``safe_dump`` (#116).

    Args:
        yaml_str: YAML string to format

    Returns:
        Formatted YAML string

    Raises:
        ValueError: No rendering loads back as the original value.
    """
    lines = yaml_str.split("\n")
    result = []
    i = 0

    while i < len(lines):
        match = _INFO_FIELD.match(lines[i])
        if not match:
            result.append(lines[i])
            i += 1
            continue

        indent, field_name = match.group(1), match.group(2)
        # The scalar continues on deeper-indented lines, and on blank lines inside
        # a quoted scalar (safe_dump writes an embedded newline as a blank line).
        # A sibling key sits at `indent` exactly, so it ends the block.
        block = [lines[i]]
        while i + 1 < len(lines) and (lines[i + 1].startswith(indent + " ") or not lines[i + 1].strip()):
            i += 1
            block.append(lines[i])
        # Trailing blank lines belong to whatever follows (e.g. the final newline).
        while len(block) > 1 and not block[-1].strip():
            block.pop()
            i -= 1
        i += 1

        value = yaml.safe_load("\n".join(line[len(indent) :] for line in block))[field_name]
        if not isinstance(value, str):
            result.extend(block)
            continue

        # PEP 8 inline comment: 2+ spaces before the '#'
        content, comment = value, None
        comment_match = re.search(r"\s{2,}#", value)
        if comment_match:
            content = value[: comment_match.start()].rstrip()
            comment = value[comment_match.start() :].strip()

        if field_name == "info":
            candidates = _info_candidates(indent, content, comment)
        else:
            escaped = content.replace("'", "''")
            candidates = [[f"{indent}implicit: '{escaped}'" + (f"  {comment}" if comment else "")]]
        candidates.append(_single_line(indent, field_name, content, comment))

        chosen = next((c for c in candidates if _loads_as(c, indent, field_name, content)), None)
        if chosen is None:
            raise ValueError(f"Cannot render {field_name} value {content!r} as YAML that loads back unchanged.")
        result.extend(chosen)

    return "\n".join(result)
