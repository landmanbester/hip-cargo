"""Function introspection for extracting cab information."""

import ast
import importlib
import importlib.metadata
import sys
from itertools import compress
from pathlib import Path
from types import NoneType, UnionType
from typing import Any, Literal, NewType, Union, get_args, get_origin

import typer
from typing_extensions import Annotated
from typing_extensions import get_origin as get_origin_ext

MS = NewType("MS", Path)
Directory = NewType("Directory", Path)
File = NewType("File", Path)
URI = NewType("URI", Path)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def generate_container_url(pyproject_path="pyproject.toml"):
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    version = project.get("version")

    # Repository URL can be in different places
    urls = project.get("urls", {})
    repo_url = urls.get("Repository") or urls.get("Source") or urls.get("Homepage")

    container_url = repo_url.replace("https://github.com", "ghcr.io") + f":{version}"

    return container_url


def get_safe_namespace():
    """Create a namespace with allowed types."""
    namespace = {
        # Basic Python types
        "int": int,
        "str": str,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "bytes": bytes,
        "None": None,
        # Typing module
        "Optional": __import__("typing").Optional,
        "Union": __import__("typing").Union,
        "List": __import__("typing").List,
        "Dict": __import__("typing").Dict,
        "Tuple": __import__("typing").Tuple,
        "Set": __import__("typing").Set,
        "Any": __import__("typing").Any,
        "Annotated": __import__("typing").Annotated,
        "Literal": __import__("typing").Literal,
        # Typer types
        "typer": typer,
        "FileText": typer.FileText,
        "FileTextWrite": typer.FileTextWrite,
        "FileBinaryRead": typer.FileBinaryRead,
        "FileBinaryWrite": typer.FileBinaryWrite,
        # paths and stimela types
        "Path": Path,
        "MS": MS,
        "Directory": Directory,
        "File": File,
        "URI": URI,
    }

    # Add any other typer types you need
    for attr in dir(typer):
        obj = getattr(typer, attr)
        if isinstance(obj, type) or attr.startswith("File"):
            namespace[attr] = obj

    return namespace


def eval_annotation_safe(annotation_str: str) -> object:
    """Evaluate annotation with controlled namespace."""
    namespace = get_safe_namespace()
    try:
        return eval(annotation_str, {"__builtins__": {}}, namespace)
    except Exception as e:
        print(f"Error evaluating annotation: {annotation_str}")
        raise e


def _get_container_image_url(module_path: str) -> str | None:
    """
    Get the container image URL for a package.

    Extracts the package name from the module path, gets the version,
    and constructs the ghcr.io image URL from the repository metadata.

    Args:
        module_path: Dotted module path (e.g., 'hip_cargo.cli.generate_cab')

    Returns:
        Container image URL (e.g., 'ghcr.io/landmanbester/hip-cargo:0.1.1')
        or None if information cannot be determined
    """
    # Extract package name (first component of module path)
    package_name = module_path.split(".")[0]

    try:
        # Get package version
        version = importlib.metadata.version(package_name)

        # Get package metadata to find repository URL
        metadata = importlib.metadata.metadata(package_name)
        repository_url = None

        # Try to get Repository URL from project URLs
        for line in metadata.get_all("Project-URL") or []:
            if line.startswith("Repository,"):
                repository_url = line.split(",", 1)[1].strip()
                break

        # If no Repository URL, try Homepage
        if not repository_url:
            for line in metadata.get_all("Project-URL") or []:
                if line.startswith("Homepage,"):
                    repository_url = line.split(",", 1)[1].strip()
                    break

        if not repository_url:
            return None

        # Extract owner/repo from GitHub URL
        # Expected format: https://github.com/owner/repo
        if "github.com" in repository_url:
            parts = repository_url.rstrip("/").split("/")
            if len(parts) >= 2:
                owner = parts[-2]
                repo = parts[-1].replace(".git", "")
                return f"ghcr.io/{owner}/{repo}:{version}"

        return None

    except (importlib.metadata.PackageNotFoundError, Exception):
        return None


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


def extract_input(arg: ast.arg, default: Any) -> tuple[str, dict[str, Any]]:
    """
    Extract input schema from a single function parameter AST node.

    Args:
        arg: AST argument node to analyze
        default: Default value for this parameter (or inspect._empty if required)

    Returns:
        Tuple of (param_name, input_def) where input_def is a dictionary
        with input configuration (dtype, info, required, default, policies)
    """
    param_name = arg.arg

    # Get type annotation
    if arg.annotation is not None:
        annotation_str = ast.unparse(arg.annotation)
        param_type = eval_annotation_safe(annotation_str)
    else:
        param_type = str

    # Unwrap Optional[Annotated[...]] to just Annotated[...]
    param_type, was_wrapped = _unwrap_optional_from_annotated(param_type)

    # Extract dtype and typer metadata
    if get_origin_ext(param_type) is Annotated:
        dtype, typer_metadata = get_args(param_type)
    else:  # old style
        raise ValueError("Only Annotated types are supported")

    # Get parameter description from typer metadata
    # param_info = typer_metadata.help if hasattr(typer_metadata, 'help') else None
    param_info = getattr(typer_metadata, "help", None)

    # Build input definition
    input_def = {}

    # Only add info field if it has a value (stimela doesn't support null)
    if param_info:
        input_def["info"] = param_info

    # Convert dtype to string (handling Union, Literal, etc. and converting to old style)
    dtype = _dtype_to_str(dtype)

    if dtype != "str" and dtype != "NoneType":
        # if it's a Literal we add a choices field and assume param dtype is str
        if "Literal" in dtype:
            input_def["choices"] = ast.literal_eval(dtype.removeprefix("Literal").strip())
        else:
            input_def["dtype"] = dtype

    # Get default value
    if default is not None:
        default = ast.literal_eval(default)
    elif hasattr(typer_metadata, "default"):
        # first case deals with flag style options
        default = getattr(typer_metadata, "default")
    else:
        raise RuntimeError("We should not end up here. This is a bug!")

    # Determine if required
    required = default is ...

    # Add required field if True
    if required:
        input_def["required"] = True
        input_def["policies"] = {}
        input_def["policies"]["positional"] = True
        if get_origin(dtype) is list:
            input_def["policies"]["repeat"] = "list"
    else:
        # only set default if not required
        if default is not None:
            input_def["default"] = default
        if get_origin(dtype) is list:
            input_def["policies"] = {}
            input_def["policies"]["repeat"] = "list"

    return param_name, input_def


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


def parse_decorator(dec: ast.expr) -> dict:
    """Parse a decorator node to extract name and arguments."""
    if isinstance(dec, ast.Name):
        # Simple decorator: @decorator
        decorator_name = dec.id
        return decorator_name, {"args": [], "kwargs": {}}

    elif isinstance(dec, ast.Call):
        # Decorator with arguments: @decorator(arg1, arg2, key=value)
        decorator_name = ast.unparse(dec.func)
        args = [ast.unparse(arg) for arg in dec.args]
        kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in dec.keywords}
        if decorator_name != "stimela_cab":
            decorator_name = kwargs.pop("name")
        return decorator_name, {"args": args, "kwargs": kwargs}

    else:
        # Complex decorator (e.g., chained attributes)
        raise ValueError("Unsupported decorator format")
