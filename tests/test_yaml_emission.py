"""Cab YAML emission regression tests (issues #109 and #110).

Two ways ``generate-cabs`` could produce a cab that is wrong or unloadable:

* a signed numeric default stringified into ``default: '-1'`` under a numeric
  ``dtype`` (#109) — invisible to the round-trip test, because the reverse
  generator casts it back using the dtype;
* a colon inside a multi-sentence ``help=``, which used to be quoted line by
  line and broke the surrounding multi-line plain scalar (#110);
* YAML that parses but means something else: a trailing colon, ``#``, a
  leading ``-`` or non-ASCII in ``help=``, and non-literal numeric defaults
  (#116).
"""

from pathlib import Path

import libcst as cst
import pytest
import yaml

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_schemas import generate_schemas
from hip_cargo.utils.introspector import format_info_fields, get_cst_value

FIXTURE_CLI = Path("tests/fixtures/src/fixture_pkg/cli/yaml_emission_demo.py")


def _expr(code: str) -> cst.BaseExpression:
    """Parse a Python expression into a CST node."""
    return cst.parse_expression(code)


def _cab_inputs(tmp_path: Path) -> dict:
    """Generate the fixture cab and return its inputs mapping."""
    cab_dir = tmp_path / "cabs"
    cab_dir.mkdir()
    generate_cabs([FIXTURE_CLI], output_dir=cab_dir)
    with open(cab_dir / "yaml_emission_demo.yml") as f:
        return yaml.safe_load(f)["cabs"]["yaml_emission_demo"]["inputs"]


# --- #109: signed numeric defaults -----------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        ("-1", -1),
        ("+1", 1),
        ("-1.5", -1.5),
        ("+2.5", 2.5),
        ("~0", -1),
        ("-0", 0),
    ],
)
def test_get_cst_value_resolves_signed_literals(code, expected):
    """Unary operations on numeric literals evaluate, not stringify."""
    value = get_cst_value(_expr(code))
    assert value == expected
    assert type(value) is type(expected)


@pytest.mark.parametrize("code", ["-x", "-foo()", "not True"])
def test_get_cst_value_falls_back_for_non_numeric_unary(code):
    """Unary operations we cannot evaluate still fall back to source text."""
    assert get_cst_value(_expr(code)) == code


def test_signed_defaults_keep_their_type_in_cab_yaml(tmp_path):
    """A negative default must not become a quoted string (#109)."""
    inputs = _cab_inputs(tmp_path)

    assert inputs["neg-int"]["default"] == -1
    assert isinstance(inputs["neg-int"]["default"], int)
    assert inputs["neg-float"]["default"] == -1.5
    assert isinstance(inputs["neg-float"]["default"], float)
    # The positive case never regressed; pin it so it cannot.
    assert inputs["pos-int"]["default"] == 7
    assert isinstance(inputs["pos-int"]["default"], int)


def test_signed_defaults_keep_their_type_in_generated_schemas(tmp_path):
    """The same bug leaked into generate-schemas via the shared IR (#109)."""
    out_dir = tmp_path / "schemas"
    generate_schemas([FIXTURE_CLI], output_dir=out_dir)

    source = (out_dir / "yaml_emission_demo.py").read_text()
    assert "default=-1" in source
    assert 'default="-1"' not in source


# --- #110: colons in info fields -------------------------------------------


def test_colon_in_multi_sentence_info_stays_parseable(tmp_path):
    """A colon in a multi-sentence help must not break the YAML block (#110)."""
    inputs = _cab_inputs(tmp_path)

    assert inputs["colon-single"]["info"] == "Antenna 1: plot only this antenna."
    assert inputs["colon-multi"]["info"] == "Antenna 1: plot only this antenna. Defaults to all of them."
    assert inputs["apostrophe-colon"]["info"] == "Note: don't quote this. It has a second sentence."


def test_format_info_fields_quotes_multi_line_values_as_a_whole():
    """Quoting must wrap the whole scalar, not each line (#110)."""
    formatted = format_info_fields("      info: 'One: two. Three.'\n")

    assert yaml.safe_load(formatted) == {"info": "One: two. Three."}
    # One opening and one closing quote for the whole value, not one pair per line.
    assert formatted.count("'") == 2


def test_generate_cabs_rejects_unparseable_output(tmp_path, monkeypatch):
    """The generation-time guard fails loudly instead of writing a broken cab."""
    monkeypatch.setattr(
        "hip_cargo.core.generate_cabs.format_info_fields",
        lambda _: "cabs:\n  demo:\n    info:\n      'a: b'\n      c\n",
    )
    with pytest.raises(ValueError, match="not parseable"):
        generate_cabs([FIXTURE_CLI], output_dir=tmp_path / "cabs")


# --- #116: valid YAML that means something else -----------------------------


def _write_module(tmp_path: Path, body: str) -> Path:
    """Write a one-command CLI module at the src/<pkg>/cli/ path generate-cabs expects."""
    cli = tmp_path / "src" / "demo_pkg" / "cli" / "demo.py"
    cli.parent.mkdir(parents=True)
    cli.write_text(
        "from typing import Annotated\n\n"
        "import typer\n\n"
        "from hip_cargo import stimela_cab\n\n\n"
        '@stimela_cab(name="demo", info="Demo.")\n'
        f"def demo(\n{body}):\n"
        "    pass\n"
    )
    return cli


def _generate(tmp_path: Path, body: str) -> tuple[str, dict]:
    """Generate the cab for a one-command module; return its text and its inputs."""
    cli = _write_module(tmp_path, body)
    cab_dir = tmp_path / "cabs"
    generate_cabs([cli], output_dir=cab_dir)
    text = (cab_dir / "demo.yml").read_text()
    return text, yaml.safe_load(text)["cabs"]["demo"]["inputs"]


@pytest.mark.parametrize(
    "help_text",
    [
        "Weights column. Options are as follows:",
        "Options are as follows:",
        "Use channel #3. Second sentence.",
        "- leading dash. Second sentence.",
        "Angle in degrees (°). Second sentence.",
        "Wavelength λ in μm. Second sentence.",
        "It's here: really. Second sentence.",
        "Plain sentence. Another plain one.",
    ],
)
def test_info_loads_back_as_the_help_string(tmp_path: Path, help_text: str) -> None:
    """The cab's info must load as exactly the help string, not merely parse (#116)."""
    text, inputs = _generate(tmp_path, f'    x: Annotated[int, typer.Option(help="{help_text}")] = 1,\n')

    assert inputs["x"]["info"] == help_text
    assert "\\x" not in text and "\\u" not in text


def test_info_keeps_its_trailing_comment_when_it_falls_back(tmp_path: Path) -> None:
    """The single-line fallback still puts the inline comment outside the scalar."""
    body = (
        "    x: Annotated[\n"
        "        int,\n"
        "        typer.Option(\n"
        '            help="Options are as follows:"  # noqa: E501\n'
        "        ),\n"
        "    ] = 1,\n"
    )
    text, inputs = _generate(tmp_path, body)

    assert inputs["x"]["info"] == "Options are as follows:"
    assert "# noqa: E501" in text


@pytest.mark.parametrize(
    "help_text",
    [
        "Plain sentence. Another plain one.",
        "Options are as follows:",
        "Angle in degrees (°). Second sentence.",
    ],
)
def test_cli_to_cab_to_cli_round_trips(tmp_path: Path, help_text: str) -> None:
    """Whatever form the cab takes, generate-function turns it back into the same help."""
    from hip_cargo.core.generate_function import generate_function

    _generate(tmp_path, f'    x: Annotated[int, typer.Option(help="{help_text}")] = 1,\n')
    regenerated = tmp_path / "regen" / "src" / "demo_pkg" / "cli" / "demo.py"
    generate_function(tmp_path / "cabs" / "demo.yml", output_file=regenerated)
    cab_again = tmp_path / "cabs_again"
    generate_cabs([regenerated], output_dir=cab_again)

    assert yaml.safe_load((cab_again / "demo.yml").read_text())["cabs"]["demo"]["inputs"]["x"]["info"] == help_text


def test_format_info_fields_escapes_apostrophes_in_implicit() -> None:
    formatted = format_info_fields("      implicit: '{current.prefix}''s.fits'\n")

    assert yaml.safe_load(formatted) == {"implicit": "{current.prefix}'s.fits"}


@pytest.mark.parametrize(
    "annotation,default",
    [
        ("int", "SENTINEL"),
        ("float", 'float("inf")'),
        ("int | None", "SENTINEL"),
        ("bool", "FLAG"),
    ],
)
def test_non_literal_numeric_default_is_rejected(tmp_path: Path, annotation: str, default: str) -> None:
    """A numeric cab default must be a value, not the source text of an expression (#116)."""
    body = f'    x: Annotated[{annotation}, typer.Option(help="X.")] = {default},\n'
    with pytest.raises(ValueError, match="not a literal"):
        _generate(tmp_path, body)


def test_non_literal_default_is_still_allowed_for_non_numeric_dtypes(tmp_path: Path) -> None:
    """The source-text fallback stays for other dtypes, e.g. a str constant."""
    _, inputs = _generate(tmp_path, '    x: Annotated[str, typer.Option(help="X.")] = DEFAULT_NAME,\n')
    assert inputs["x"]["default"] == "DEFAULT_NAME"


def test_non_literal_numeric_default_in_typer_option_is_rejected(tmp_path: Path) -> None:
    """``typer.Option(default=...)`` is checked like ``= default`` (#116 review)."""
    body = '    x: Annotated[float, typer.Option(default=float("inf"), help="X.")],\n'
    with pytest.raises(ValueError, match="not a literal"):
        _generate(tmp_path, body)


@pytest.mark.parametrize(
    "help_source,expected",
    [
        (r"Line one.\nLine two.", "Line one.\nLine two."),
        (r"Options: a.\n\nThen b.", "Options: a.\n\nThen b."),
    ],
)
def test_help_with_embedded_newlines_loads_back(tmp_path: Path, help_source: str, expected: str) -> None:
    """safe_dump writes these as quoted scalars with blank continuation lines."""
    text, inputs = _generate(
        tmp_path,
        f'    x: Annotated[int, typer.Option(help="{help_source}")] = 1,\n'
        '    y: Annotated[int, typer.Option(help="After.")] = 2,\n',
    )

    assert inputs["x"]["info"] == expected
    assert inputs["y"] == {"info": "After.", "dtype": "int", "default": 2}
    assert not any(line != line.rstrip() for line in text.splitlines()), "no trailing whitespace"
