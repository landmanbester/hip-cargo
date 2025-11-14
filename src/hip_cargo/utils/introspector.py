"""Function introspection for extracting cab information."""

import importlib
import inspect
import re
import sys
from ast import literal_eval
from itertools import compress
from pathlib import Path
from types import NoneType, UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from typing_extensions import Annotated
from typing_extensions import get_origin as get_origin_ext


def get_function_from_module(module_path: str) -> tuple[Any, str]:
    """
    Import a module and find the decorated function.

    Args:
        module_path: Dotted module path (e.g., 'package.module')

    Returns:
        Tuple of (function, module_path)

    Raises:
        ImportError: If module cannot be imported
        ValueError: If no decorated function is found
    """
    # Add current working directory to Python path if not already there
    # This allows importing modules relative to where the command is run
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        # Provide a more helpful error message
        raise ImportError(
            f"Could not import module '{module_path}'. "
            f"Make sure the module exists and is importable from the current directory."
        ) from e

    # Look for a function with __stimela_cab_config__
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if hasattr(obj, "__stimela_cab_config__"):
            return obj, module_path

    raise ValueError(f"No function decorated with @stimela_cab found in {module_path}")


def extract_cab_info(func: Any) -> dict[str, Any]:
    """
    Extract cab configuration from a decorated function.

    Args:
        func: Function decorated with @stimela_cab

    Returns:
        Dictionary with cab information
    """
    if not hasattr(func, "__stimela_cab_config__"):
        raise ValueError("Function must be decorated with @stimela_cab")

    cab_config = func.__stimela_cab_config__

    # Get the module path for the command
    module_path = func.__module__
    # replace .cli. with .core. so stimela calls the core function
    module_path = module_path.replace(".cli.", ".core.")
    func_name = func.__name__
    command = f"({module_path}){func_name}"

    # Extract docstring
    docstring = inspect.getdoc(func) or cab_config.get("info", "")
    # Use first line as info if available
    info = docstring.split("\n")[0] if docstring else cab_config.get("info", "")

    # Start building the cab definition
    cab_def = {
        "flavour": "python",
        "command": command,
        "info": info,
        "policies": {
            "pass_missing_as_none": True,
            **cab_config.get("policies", {}),
        },
    }

    return cab_def


def _unwrap_optional_from_annotated(param_type: Any) -> tuple[Any, bool]:
    """
    Unwrap Optional wrapper from Annotated types.

    Python automatically wraps `Annotated[T | None, ...] = None` as `Optional[Annotated[T | None, ...]]`.
    This function detects and unwraps that pattern.

    Args:
        param_type: The parameter type hint to unwrap

    Returns:
        Tuple of (unwrapped_type, was_wrapped)
    """
    origin = get_origin(param_type)

    # Check if it's Optional (which is Union[X, None])
    if origin is Union:
        args = get_args(param_type)
        # Check if it's a Union with exactly 2 args where one is NoneType
        if len(args) == 2 and NoneType in args:
            # This is Optional[X] - extract the non-None type
            non_none_arg = args[0] if args[1] is NoneType else args[1]
            # If the non-None arg is Annotated, we've found our pattern
            if get_origin_ext(non_none_arg) is Annotated:
                return non_none_arg, True

    return param_type, False


def extract_inputs(func: Any) -> dict[str, Any]:
    """
    Extract input schema from function signature.

    Args:
        func: Function to analyze

    Returns:
        Dictionary of input parameters
    """
    sig = inspect.signature(func)
    type_hints = get_type_hints(func, include_extras=True)

    inputs = {}
    for param_name, param in sig.parameters.items():
        if param_name == "self" or param_name == "cls":
            continue

        # Get type hint
        param_type = type_hints.get(param_name, str)

        # Unwrap Optional[Annotated[...]] to just Annotated[...]
        param_type, was_wrapped = _unwrap_optional_from_annotated(param_type)

        if get_origin_ext(param_type) is Annotated:
            dtype, typer_metadata = get_args(param_type)
            if typer_metadata.__class__.__name__ == "ArgumentInfo":
                is_argument = True
            elif typer_metadata.__class__.__name__ == "OptionInfo":
                is_argument = False
        else:  # old style
            dtype = param_type
            typer_metadata = param.default

        dtype = _dtype_to_str(dtype)

        # Get parameter description from docstring
        param_info = typer_metadata.help
        if param_info and "Stimela dtype" in param_info:
            idx = param_info.find("Stimela")
            dtype = param_info[idx:].split(":")[-1].strip()
            param_info = param_info[0:idx]

        input_def = {"info": param_info}

        if dtype != "str" and dtype != "NoneType":
            # if it's a Literal we add a choices field and assume param dtype is str
            if "Literal" in dtype:
                input_def["choices"] = literal_eval(dtype.removeprefix("Literal").strip())
            else:
                input_def["dtype"] = dtype

        # Get default value (note - only fall back to typer_metadata if the param does not have a default)
        if param.default is inspect._empty:
            default = getattr(typer_metadata, "default", None)
        else:
            default = param.default

        # Determine if required
        required = default is ...

        # Build input definition
        if required:
            input_def["required"] = True

        # Add default value if it exists and is not ...
        if not required and default is not None:
            input_def["default"] = default

        # Add policies based on type and Typer decorator
        policies = _infer_parameter_policies(dtype, param_info, is_argument)
        if policies:
            input_def["policies"] = policies

        inputs[param_name] = input_def

    return inputs


def extract_outputs(func: Any) -> dict[str, Any]:
    """
    Extract output schema from @stimela_output decorators.

    Args:
        func: Function to analyze

    Returns:
        Dictionary of output parameters
    """
    if not hasattr(func, "__stimela_outputs__"):
        return {}

    outputs = {}
    for output in func.__stimela_outputs__:
        outputs[output["name"]] = {
            "dtype": output["dtype"],
            "info": output["info"],
            "required": output["required"],
            "implicit": output["implicit"],
        }

    return outputs


def _parse_google_docstring(docstring: str) -> dict[str, str]:
    """
    Parse Google-style docstring to extract parameter descriptions.

    Args:
        docstring: The docstring to parse

    Returns:
        Dictionary mapping parameter names to descriptions
    """
    param_docs = {}

    # Look for Args section
    args_match = re.search(r"Args:\s*\n(.*?)(?:\n\n|\n[A-Z]|\Z)", docstring, re.DOTALL)
    if not args_match:
        return param_docs

    args_section = args_match.group(1)

    # Parse each parameter line
    for line in args_section.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Match pattern: param_name: description
        match = re.match(r"(\w+):\s*(.+)", line)
        if match:
            param_name = match.group(1)
            description = match.group(2)
            param_docs[param_name] = description

    return param_docs


def _infer_parameter_policies(python_type: Any, param_info: str, is_argument: bool = False) -> dict[str, Any]:
    """
    Infer parameter policies from type and info.

    Args:
        python_type: The Python type hint
        param_info: Parameter description
        is_argument: Whether this is a Typer Argument (positional)

    Returns:
        Dictionary of policies
    """
    policies = {}

    # Typer Arguments are positional
    if is_argument:
        policies["positional"] = True

    # Check if it's a list type
    origin = get_origin(python_type)
    if origin is list:
        policies["repeat"] = "list"

    return policies


def _dtype_to_str(dtype):
    # strip out None
    origin = get_origin(dtype)
    opts = get_args(dtype)

    def is_none(x):
        return x is not NoneType

    mask = list(map(is_none, opts))
    opts = tuple(compress(opts, mask))

    # convert type1 | type2 to old Union type and discard None
    if origin is UnionType or origin is Union:  # the latter is required to handle Optional
        if len(opts) == 1:  # discard Union
            dtype = opts[0]
        else:
            dtype = Union[opts]

    # convert to string
    origin = get_origin(dtype)
    opts = get_args(dtype)

    # we use this mappng since stimela only accepts the uppercase typing versions
    origin_to_typing = {
        list: "List",
        dict: "Dict",
        set: "Set",
        tuple: "Tuple",
        str: "str",
        int: "int",
        float: "float",
        bool: "bool",
    }

    if origin is Literal:
        # Literal args are actual values, not types
        formatted_args = ", ".join(repr(opt) for opt in opts)
        return f"Literal[{formatted_args}]"

    if origin and opts:
        # Recursively handle nested generics
        formatted_args = ", ".join(_dtype_to_str(opt) for opt in opts)
        return f"{origin_to_typing[origin]}[{formatted_args}]"

    # Handle basic types
    if hasattr(dtype, "__name__"):
        return dtype.__name__
    return dtype
