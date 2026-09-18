"""Cab YAML emission regression tests (issues #109 and #110).

Two ways ``generate-cabs`` could produce a cab that is wrong or unloadable:

* a signed numeric default stringified into ``default: '-1'`` under a numeric
  ``dtype`` (#109) — invisible to the round-trip test, because the reverse
  generator casts it back using the dtype;
* a colon inside a multi-sentence ``help=``, which used to be quoted line by
  line and broke the surrounding multi-line plain scalar (#110).
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
