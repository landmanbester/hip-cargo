"""Tests for first-class comma-separated list types (ListInt, ListFloat, ListStr)."""

import tempfile
from pathlib import Path

import libcst as cst
import yaml

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function
from hip_cargo.utils.cab_to_function import (
    generate_function_body,
    generate_parameter_signature,
)
from hip_cargo.utils.introspector import extract_input_libcst
from hip_cargo.utils.types import (
    parse_list_float,
    parse_list_int,
    parse_list_str,
)

# --- Parser function tests ---


def test_parse_list_int_basic():
    assert parse_list_int("1,2,3") == [1, 2, 3]


def test_parse_list_int_with_spaces():
    assert parse_list_int("1, 2, 3") == [1, 2, 3]


def test_parse_list_int_single():
    assert parse_list_int("42") == [42]


def test_parse_list_float_basic():
    assert parse_list_float("1.5,2.5,3.5") == [1.5, 2.5, 3.5]


def test_parse_list_float_with_spaces():
    assert parse_list_float("1.5, 2.5, 3.5") == [1.5, 2.5, 3.5]


def test_parse_list_str_basic():
    assert parse_list_str("a,b,c") == ["a", "b", "c"]


def test_parse_list_str_with_spaces():
    assert parse_list_str("a, b, c") == ["a", "b", "c"]


def test_parse_list_str_glob_safety():
    """Verify parse_list_str does NOT expand globs."""
    result = parse_list_str("foo-*.py, bar-*.py")
    assert result == ["foo-*.py", "bar-*.py"]


# --- Introspector tests ---


def test_introspector_listint_maps_to_list_int():
    """ListInt type hint correctly maps to List[int] dtype."""
    code = """
from typing import Annotated
import typer
from hip_cargo.utils.types import ListInt, parse_list_int

def foo(
    indices: Annotated[
        ListInt,
        typer.Option(..., parser=parse_list_int, help="Channel indices"),
    ],
):
    pass
"""
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]

    param_name, input_def = extract_input_libcst(cst_param)

    assert param_name == "indices"
    assert input_def["dtype"] == "List[int]"


def test_introspector_listfloat_maps_to_list_float():
    """ListFloat type hint correctly maps to List[float] dtype."""
    code = """
from typing import Annotated
import typer
from hip_cargo.utils.types import ListFloat, parse_list_float

def foo(
    weights: Annotated[
        ListFloat,
        typer.Option(parser=parse_list_float, help="Weights"),
    ] = "1.0,1.0",
):
    pass
"""
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]

    param_name, input_def = extract_input_libcst(cst_param)

    assert param_name == "weights"
    assert input_def["dtype"] == "List[float]"


def test_introspector_liststr_maps_to_list_str():
    """ListStr type hint correctly maps to List[str] dtype."""
    code = """
from typing import Annotated
import typer
from hip_cargo.utils.types import ListStr, parse_list_str

def foo(
    names: Annotated[
        ListStr,
        typer.Option(parser=parse_list_str, help="Names"),
    ] = "a,b,c",
):
    pass
"""
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]

    param_name, input_def = extract_input_libcst(cst_param)

    assert param_name == "names"
    assert input_def["dtype"] == "List[str]"


# --- cab_to_function tests ---


def test_generate_parameter_signature_list_int():
    """List[int] dtype generates ListInt type with parse_list_int parser."""
    param_def = {
        "dtype": "List[int]",
        "info": "Channel indices",
        "required": True,
    }
    sig = generate_parameter_signature("indices", param_def)

    assert "ListInt" in sig
    assert "parse_list_int" in sig
    assert "str" not in sig.split("Annotated[")[1].split(",")[0]  # type is not str


def test_generate_parameter_signature_list_float():
    """List[float] dtype generates ListFloat type with parse_list_float parser."""
    param_def = {
        "dtype": "List[float]",
        "info": "Weights",
        "default": "1.0,1.0",
    }
    sig = generate_parameter_signature("weights", param_def)

    assert "ListFloat" in sig
    assert "parse_list_float" in sig


def test_generate_parameter_signature_list_str():
    """List[str] dtype generates ListStr type with parse_list_str parser."""
    param_def = {
        "dtype": "List[str]",
        "info": "Names",
        "default": "a,b,c",
    }
    sig = generate_parameter_signature("names", param_def)

    assert "ListStr" in sig
    assert "parse_list_str" in sig


def test_no_stimela_dict_for_list_types():
    """ListType params should NOT generate a stimela metadata dict."""
    param_def = {
        "dtype": "List[int]",
        "info": "Channel indices",
        "required": True,
    }
    sig = generate_parameter_signature("indices", param_def)

    assert "stimela" not in sig


def test_generate_function_body_no_comma_conversion():
    """Function body should NOT contain manual comma-splitting for List[int] params."""
    cab_def = {"command": "my_pkg.core.process.process_data"}
    inputs = {
        "indices": {"dtype": "List[int]", "info": "Indices", "required": True},
        "name": {"dtype": "str", "info": "Name", "required": True},
    }
    outputs = {}

    body_lines = generate_function_body(cab_def, inputs, outputs)
    body_text = "\n".join(body_lines)

    assert "split" not in body_text
    assert "strip" not in body_text
    assert "indices_list" not in body_text
    # Parameters should be passed directly
    assert "indices," in body_text


# --- Full roundtrip test ---


def test_roundtrip_listint():
    """CLI with ListInt -> YAML -> CLI preserves ListInt with parser."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        cli_dir = tmpdir / "src" / "test_pkg" / "cli"
        cli_dir.mkdir(parents=True)
        test_file = cli_dir / "test_list.py"

        test_code = '''from pathlib import Path
from typing import Annotated

import typer

from hip_cargo.utils.decorators import stimela_cab
from hip_cargo.utils.types import ListInt, parse_list_int


@stimela_cab(
    name="test_list",
    info="Test list types.",
)
def test_list(
    indices: Annotated[
        ListInt,
        typer.Option(..., parser=parse_list_int, help="Channel indices"),
    ],
    name: Annotated[
        str,
        typer.Option(..., help="Name"),
    ],
):
    """Test command."""
    pass
'''
        test_file.write_text(test_code)

        # Step 1: CLI -> YAML
        generate_cabs([test_file], output_dir=tmpdir)

        cab_file = tmpdir / "test_list.yml"
        with open(cab_file) as f:
            yaml_content = f.read()

        # Verify YAML has List[int] dtype
        data = yaml.safe_load(yaml_content)
        assert data["cabs"]["test_list"]["inputs"]["indices"]["dtype"] == "List[int]"

        # Step 2: YAML -> CLI
        gen_file = tmpdir / "test_list_generated.py"
        generate_function(cab_file=cab_file, output_file=gen_file, config_file=Path("pyproject.toml"))

        with open(gen_file) as f:
            python_code = f.read()

        # Verify generated code uses ListInt + parse_list_int
        assert "ListInt" in python_code
        assert "parse_list_int" in python_code
        assert "from hip_cargo import" in python_code
        # Should NOT have manual comma splitting
        assert "split" not in python_code or 'split(",")' not in python_code
        # Should NOT have a stimela metadata dict for this parameter
        # (the dtype is inferred from ListInt)


def test_roundtrip_listfloat_optional():
    """CLI with optional ListFloat -> YAML -> CLI roundtrip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        cli_dir = tmpdir / "src" / "test_pkg" / "cli"
        cli_dir.mkdir(parents=True)
        test_file = cli_dir / "test_listfloat.py"

        test_code = '''from pathlib import Path
from typing import Annotated

import typer

from hip_cargo.utils.decorators import stimela_cab
from hip_cargo.utils.types import ListFloat, parse_list_float


@stimela_cab(
    name="test_listfloat",
    info="Test list float.",
)
def test_listfloat(
    weights: Annotated[
        ListFloat,
        typer.Option(parser=parse_list_float, help="Weights"),
    ] = "1.0,2.0",
):
    """Test command."""
    pass
'''
        test_file.write_text(test_code)

        # CLI -> YAML
        generate_cabs([test_file], output_dir=tmpdir)

        cab_file = tmpdir / "test_listfloat.yml"
        data = yaml.safe_load(cab_file.read_text())
        assert data["cabs"]["test_listfloat"]["inputs"]["weights"]["dtype"] == "List[float]"

        # YAML -> CLI
        gen_file = tmpdir / "test_listfloat_generated.py"
        generate_function(cab_file=cab_file, output_file=gen_file, config_file=Path("pyproject.toml"))

        python_code = gen_file.read_text()
        assert "ListFloat" in python_code
        assert "parse_list_float" in python_code
