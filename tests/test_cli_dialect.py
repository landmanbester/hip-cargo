"""The CLI dialect hip-cargo can round-trip, enforced at parse time (#112, #113).

A cab and a CLI module are two renderings of one definition, and hip-cargo
generates either from the other. A CLI module may therefore only use constructs a
cab can express. ``typer.Argument`` and ``typer.Option`` param_decls cannot be, so
they are rejected here — rather than mis-parsed into the cab (#112) or left to
surface later as a round-trip line diff (#113).
"""

from pathlib import Path

import libcst as cst
import pytest

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.utils.introspector import extract_param_spec


def _param(source: str) -> cst.Param:
    """Parse a single annotated parameter into a CST param node."""
    module = cst.parse_module(f"def f(\n    {source},\n): ...\n")
    return module.body[0].params.params[0]


# --- #112: param_decls ------------------------------------------------------


def test_short_flags_on_a_required_option_are_rejected():
    """The decl must not be mistaken for the default (#112)."""
    param = _param('ex: Annotated[str, typer.Option("-x", "--ex", help="An option.")]')

    with pytest.raises(ValueError, match="param_decls"):
        extract_param_spec(param)


def test_short_flags_on_an_optional_option_are_rejected():
    """A Python default masks the mis-parse but still breaks the round trip (#112)."""
    param = _param('datacolumn: Annotated[str, typer.Option("--datacolumn", "-d", help="A column.")] = "DATA"')

    with pytest.raises(ValueError, match="param_decls"):
        extract_param_spec(param)


def test_the_param_decl_error_names_the_parameter_and_the_decls():
    """An actionable message, not an internal invariant."""
    param = _param('ex: Annotated[str, typer.Option("-x", "--ex", help="An option.")]')

    with pytest.raises(ValueError) as excinfo:
        extract_param_spec(param)

    message = str(excinfo.value)
    assert "'ex'" in message
    assert "'-x'" in message
    assert "'--ex'" in message


def test_a_decl_after_the_ellipsis_is_rejected_too():
    """The ellipsis is the required marker; anything after it is still a decl."""
    param = _param('ex: Annotated[str, typer.Option(..., "-x", help="An option.")]')

    with pytest.raises(ValueError, match="param_decls"):
        extract_param_spec(param)


def test_generate_cabs_refuses_a_module_with_param_decls(tmp_path):
    """It must fail rather than write a cab with the flag as the default (#112)."""
    cli_dir = tmp_path / "src" / "probe_pkg" / "cli"
    cli_dir.mkdir(parents=True)
    (cli_dir / "probe.py").write_text(
        "from typing import Annotated\n\n"
        "import typer\n\n"
        "from hip_cargo import stimela_cab\n\n\n"
        '@stimela_cab(name="probe", info="Probe.")\n'
        "def probe(\n"
        '    ex: Annotated[str, typer.Option("-x", "--ex", help="An option.")],\n'
        "):\n"
        '    """Probe."""\n'
        "    print(ex)\n"
    )

    with pytest.raises(ValueError, match="param_decls"):
        generate_cabs([cli_dir / "probe.py"], output_dir=tmp_path / "cabs")

    assert not (tmp_path / "cabs" / "probe.yml").exists()


# --- #113: typer.Argument ---------------------------------------------------


def test_typer_argument_is_rejected():
    """A cab cannot express a positional CLI argument (#113)."""
    param = _param('ms: Annotated[str, typer.Argument(..., help="Measurement Set.")]')

    with pytest.raises(ValueError, match="typer.Argument"):
        extract_param_spec(param)


def test_typer_argument_without_an_ellipsis_is_rejected_the_same_way():
    """The idiomatic Annotated spelling used to raise an internal RuntimeError (#113)."""
    param = _param('ms: Annotated[str, typer.Argument(help="Measurement Set.")]')

    with pytest.raises(ValueError, match="typer.Argument"):
        extract_param_spec(param)


def test_the_argument_error_points_at_the_sanctioned_form():
    """Name the fix, not the invariant."""
    param = _param('ms: Annotated[str, typer.Argument(help="Measurement Set.")]')

    with pytest.raises(ValueError) as excinfo:
        extract_param_spec(param)

    message = str(excinfo.value)
    assert "'ms'" in message
    assert "typer.Option(..." in message


def test_a_required_option_without_its_ellipsis_names_the_fix():
    """The remaining route to the old RuntimeError, with a message that helps."""
    param = _param('ms: Annotated[str, typer.Option(help="Measurement Set.")]')

    with pytest.raises(ValueError) as excinfo:
        extract_param_spec(param)

    assert "typer.Option(..." in str(excinfo.value)


# --- the sanctioned forms must keep parsing ---------------------------------


def test_required_and_optional_options_still_parse():
    """Guard against over-rejection."""
    required = extract_param_spec(_param('ms: Annotated[str, typer.Option(..., help="Measurement Set.")]'))
    assert required.required is True

    optional = extract_param_spec(_param('n: Annotated[int, typer.Option(help="A count.")] = 7'))
    assert optional.required is False
    assert optional.default == 7


def test_a_non_string_positional_is_still_read_as_a_default():
    """Only strings are param_decls; the old positional-default form is untouched."""
    spec = extract_param_spec(_param('threshold: Annotated[float, typer.Option(0.5, help="A threshold.")]'))

    assert spec.default == 0.5


def test_the_repo_fixtures_still_parse():
    """The shipped fixture commands use the sanctioned dialect."""
    for fixture in Path("tests/fixtures/src/fixture_pkg/cli").glob("*.py"):
        if fixture.name == "__init__.py":
            continue
        module = cst.parse_module(fixture.read_text())
        for node in module.body:
            if isinstance(node, cst.FunctionDef):
                for param in node.params.params:
                    extract_param_spec(param)
