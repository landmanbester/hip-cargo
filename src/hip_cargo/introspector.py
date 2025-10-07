"""Function introspection for extracting cab information."""

import importlib
import inspect
import re
import sys
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

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


def _extract_typer_metadata(param_type: Any, default_value: Any) -> tuple[Any, Any, bool, bool]:
    """
    Extract Typer metadata from either Annotated type hint or default value.

    Args:
        param_type: The type hint (may be Annotated)
        default_value: The default value (may be Typer object)

    Returns:
        Tuple of (actual_type, typer_metadata, is_argument, is_option)
    """
    typer_metadata = None
    is_argument = False
    is_option = False
    actual_type = param_type

    # Check if type hint is Annotated
    if get_origin_ext(param_type) is Annotated:
        args = get_args(param_type)
        if args:
            actual_type = args[0]  # First arg is the actual type
            # Look for Typer metadata in the remaining args
            for metadata in args[1:]:
                if hasattr(metadata, "__class__"):
                    class_name = metadata.__class__.__name__
                    if class_name == "ArgumentInfo":
                        is_argument = True
                        typer_metadata = metadata
                        break
                    elif class_name == "OptionInfo":
                        is_option = True
                        typer_metadata = metadata
                        break

    # Check default value for Typer metadata (old style)
    if typer_metadata is None and default_value != inspect.Parameter.empty:
        if hasattr(default_value, "__class__"):
            class_name = default_value.__class__.__name__
            if class_name == "ArgumentInfo":
                is_argument = True
                typer_metadata = default_value
            elif class_name == "OptionInfo":
                is_option = True
                typer_metadata = default_value

    return actual_type, typer_metadata, is_argument, is_option


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

    # Parse docstring for parameter descriptions
    docstring = inspect.getdoc(func) or ""
    param_docs = _parse_google_docstring(docstring)

    inputs = {}

    for param_name, param in sig.parameters.items():
        if param_name == "self" or param_name == "cls":
            continue

        # Get type hint
        param_type = type_hints.get(param_name, str)

        # Extract Typer metadata from Annotated or default value
        actual_type, typer_metadata, is_argument, is_option = _extract_typer_metadata(param_type, param.default)

        # Get parameter description from docstring
        param_info = param_docs.get(param_name, "")

        # Determine dtype
        dtype = _python_type_to_stimela_dtype(actual_type, param_info)

        # Get default value
        actual_default = None
        has_default = False

        if typer_metadata is not None:
            # Get default from Typer metadata
            actual_default = getattr(typer_metadata, "default", ...)
            has_default = actual_default is not ...
        elif param.default != inspect.Parameter.empty:
            # Regular Python default
            actual_default = param.default
            has_default = True

        # Determine if required
        required = not has_default or actual_default is ...

        # Build input definition
        input_def = {
            "dtype": dtype,
            "info": param_info,
            "required": required,
        }

        # Add default value if it exists and is not ...
        if has_default and actual_default is not None and actual_default is not ...:
            input_def["default"] = actual_default

        # Add policies based on type and Typer decorator
        policies = _infer_parameter_policies(actual_type, param_info, is_argument)
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


def _python_type_to_stimela_dtype(python_type: Any, param_info: str) -> str:
    """
    Convert Python type hint to Stimela dtype.

    Args:
        python_type: The Python type hint
        param_info: Parameter description (may contain dtype hints)

    Returns:
        Stimela dtype string
    """
    # Check if info string specifies a special type
    info_lower = param_info.lower()
    if "directory" in info_lower or "dir" in info_lower:
        return "Directory"
    elif "measurement set" in info_lower or "ms" in info_lower:
        return "MS"
    elif "url" in info_lower:
        return "URL"
    elif "uri" in info_lower:
        return "URI"
    elif "file" in info_lower:
        return "File"

    # Handle Path types
    if python_type == Path or python_type == "Path":
        return "File"  # Default to File for Path types

    # Handle basic types
    origin = get_origin(python_type)

    if origin is list:
        args = get_args(python_type)
        if args:
            inner_type = _python_type_to_stimela_dtype(args[0], "")
            return f"List[{inner_type}]"
        return "List[str]"

    # Handle Optional/Union types
    if origin is type(None) or (hasattr(python_type, "__origin__") and python_type.__origin__ is type(None)):
        return "str"

    # Map basic types
    type_map = {
        str: "str",
        int: "int",
        float: "float",
        bool: "bool",
    }

    return type_map.get(python_type, "str")


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
