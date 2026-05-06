"""Core logic for generating Pydantic schemas of tunable parameters.

For each ``@stimela_cab``-decorated command with at least one parameter
carrying ``StimelaMeta(metadata={"tunable": True})``, emit a Pydantic
``BaseModel`` whose fields are the tunable subset of the CLI inputs.

Schemas are consumed downstream as ``output_type`` for ``pydantic-ai``
agents; the generated models must be importable in environments that have
``pydantic`` installed but otherwise stay out of hip-cargo's own dependency
surface.
"""

import subprocess
import warnings
from pathlib import Path

from hip_cargo.utils.introspector import parse_module
from hip_cargo.utils.spec import CommandSpec, ParamSpec
from hip_cargo.utils.types import parse_list_float, parse_list_int, parse_list_str

ALLOWED_LEAF_TYPES = {"int", "float", "str", "bool"}

LIST_NEWTYPE_TO_INNER = {
    "ListInt": "int",
    "ListFloat": "float",
    "ListStr": "str",
}

LIST_NEWTYPE_PARSERS = {
    "ListInt": parse_list_int,
    "ListFloat": parse_list_float,
    "ListStr": parse_list_str,
}


class TunableTypeError(RuntimeError):
    """Raised when a parameter marked ``tunable=True`` has an unsupported type."""


def _strip_optional(dtype_str: str) -> tuple[str, bool]:
    """Strip an outer ``| None`` / ``Optional[...]`` wrapper.

    Returns ``(inner, is_optional)``.
    """
    s = dtype_str.strip()
    if s.endswith(" | None"):
        return s[: -len(" | None")].strip(), True
    if s.startswith("None | "):
        return s[len("None | ") :].strip(), True
    if s.startswith("Optional[") and s.endswith("]"):
        return s[len("Optional[") : -1].strip(), True
    return s, False


def _to_pydantic_type(spec: ParamSpec) -> str:
    """Map a tunable parameter's :attr:`ParamSpec.dtype_str` to a pydantic field type.

    Raises:
        TunableTypeError: If the type is not in the supported whitelist.
    """
    inner, is_optional = _strip_optional(spec.dtype_str)
    inner = inner.strip()

    if inner in ALLOWED_LEAF_TYPES:
        py_type = inner
    elif inner.startswith("Literal["):
        py_type = inner
    elif inner in LIST_NEWTYPE_TO_INNER:
        py_type = f"list[{LIST_NEWTYPE_TO_INNER[inner]}]"
    elif inner.startswith("list[") and inner.endswith("]"):
        list_inner = inner[len("list[") : -1].strip()
        if list_inner not in ALLOWED_LEAF_TYPES:
            raise TunableTypeError(_unsupported_message(spec))
        py_type = inner
    else:
        raise TunableTypeError(_unsupported_message(spec))

    return f"{py_type} | None" if is_optional else py_type


def _unsupported_message(spec: ParamSpec) -> str:
    return (
        f"Tunable parameter {spec.name!r} has unsupported type {spec.dtype_str!r}. "
        f"Tunable parameters must be one of: int, float, str, bool, Literal[...], "
        f"ListInt/ListFloat/ListStr, list[int|float|str|bool], optionally wrapped in `| None`."
    )


def _normalize_default(spec: ParamSpec) -> object:
    """Resolve a parameter's default into a Python value suitable for pydantic.

    Required parameters (``default is ...``) are returned as ``...`` and
    later emitted as ``Field(...)``.

    For ``ListInt`` / ``ListFloat`` / ``ListStr`` parameters, the CLI default
    is a comma-separated string (Typer cannot natively bind a list option);
    parse it into the corresponding Python list so the schema field carries
    the list value an agent would actually emit.
    """
    if spec.default is ... or spec.default is None:
        return spec.default

    inner, _ = _strip_optional(spec.dtype_str)
    parser = LIST_NEWTYPE_PARSERS.get(inner.strip())
    if parser is None:
        return spec.default
    if not isinstance(spec.default, str):
        return spec.default
    return parser(spec.default)


def _format_pydantic_default(value: object) -> str:
    if value is ...:
        return "..."
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_pydantic_default(v) for v in value) + "]"
    return repr(value)


def _pascal_case(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def _validate_tunable(spec: ParamSpec) -> None:
    """Reject tunable params whose typer metadata makes the value opaque to a model."""
    if spec.raw_typer_meta.get("callback"):
        raise TunableTypeError(
            f"Tunable parameter {spec.name!r} has a typer callback, which can transform "
            f"the value before it reaches the function. Schemas cannot represent that."
        )


def _render_schema_module(command: CommandSpec) -> str | None:
    """Render the source of one ``<Command>Tunables`` Pydantic model.

    Returns ``None`` if the command has no tunable parameters.
    """
    tunables = command.tunable_params
    if not tunables:
        return None

    needs_literal = any("Literal[" in p.dtype_str for p in tunables)

    lines: list[str] = ['"""Auto-generated by hip-cargo. Do not edit by hand."""', ""]
    if needs_literal:
        lines += ["from typing import Literal", ""]
    lines += ["from pydantic import BaseModel, Field", "", ""]

    class_name = f"{_pascal_case(command.name)}Tunables"
    lines.append(f"class {class_name}(BaseModel):")

    for spec in tunables:
        _validate_tunable(spec)
        py_type = _to_pydantic_type(spec)
        default = _normalize_default(spec)
        description = spec.help or ""
        if spec.required:
            field_call = f"Field(..., description={description!r})"
        else:
            field_call = f"Field(default={_format_pydantic_default(default)}, description={description!r})"
        lines.append(f"    {spec.name}: {py_type} = {field_call}")

    return "\n".join(lines) + "\n"


def _ruff_format(source: str, config_file: Path | None) -> str:
    """Run ``ruff check --fix`` then ``ruff format`` on a source string.

    Falls back to the unformatted source on subprocess failure (with a
    warning) so generation never silently fails.
    """
    check_cmd = ["ruff", "check", "--fix", "--stdin-filename", "schema.py", "-"]
    format_cmd = ["ruff", "format", "--stdin-filename", "schema.py", "-"]
    cwd = None
    if config_file is not None:
        check_cmd.extend(["--config", str(config_file)])
        format_cmd.extend(["--config", str(config_file)])
        cwd = str(Path(config_file).resolve().parent)

    try:
        lint = subprocess.run(check_cmd, input=source, capture_output=True, text=True, check=True, cwd=cwd)
        fmt = subprocess.run(format_cmd, input=lint.stdout, capture_output=True, text=True, check=True, cwd=cwd)
        return fmt.stdout
    except subprocess.CalledProcessError as e:
        warnings.warn("Ruff failed during schema generation; using unformatted source.\n" + e.stderr)
        return source


def generate_schemas(
    module: list[Path],
    output_dir: Path | None = None,
    config_file: Path | None = None,
) -> None:
    """Generate Pydantic schemas of tunable parameters from Python CLI modules.

    Args:
        module: List of CLI module paths. Glob wildcards in the filename are expanded.
        output_dir: Directory to write ``<command>.py`` files into. If ``None``,
            schemas are printed to stdout.
        config_file: Optional ruff config file path used when formatting.

    Raises:
        TunableTypeError: If any tunable parameter has an unsupported type.
        RuntimeError: If module paths are invalid or yield no files.
    """
    modlist: list[Path] = []
    for modpath in module:
        modpath = Path(modpath)
        if "*" in str(modpath):
            base_path = modpath.parent
            pattern = modpath.name
            matches = [f for f in base_path.glob(pattern) if f.is_file() and not f.name.startswith("__")]
            if not matches:
                raise RuntimeError(f"No modules found matching {modpath}")
            modlist.extend(matches)
        else:
            if not modpath.is_file():
                raise RuntimeError(f"No module file found at {modpath}")
            modlist.append(modpath)

    for mod in modlist:
        print(f"Loading file: {mod}")

    if output_dir is not None:
        print(f"Writing schemas to: {output_dir}")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    for module_path in modlist:
        module_spec = parse_module(module_path)
        for command in module_spec.commands:
            source = _render_schema_module(command)
            if source is None:
                continue
            formatted = _ruff_format(source, config_file)

            if output_dir is None:
                print(formatted)
                continue

            output_file = output_dir / f"{command.name}.py"
            if output_file.exists() and output_file.read_text() == formatted:
                continue
            output_file.write_text(formatted)
