"""Tests for stimela metadata dict in Annotated type hints."""

import tempfile
from pathlib import Path

import libcst as cst

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function
from hip_cargo.utils.introspector import extract_input_libcst, extract_stimela_metadata_libcst


def test_extract_stimela_metadata_basic():
    """Test extraction of stimela dict from Annotated."""
    code = """
from typing import Annotated
import typer

def foo(
    param: Annotated[
        str,
        typer.Option(help="Test param"),
        {"stimela": {"dtype": "File", "must_exist": True}}
    ]
):
    pass
"""
    # Parse with LibCST
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]

    # Parse annotated to get metadata nodes
    from hip_cargo.utils.introspector import parse_annotated_libcst

    annotation_node = cst_param.annotation.annotation
    dtype_node, metadata_nodes = parse_annotated_libcst(annotation_node)

    # Extract stimela metadata
    stimela_meta = extract_stimela_metadata_libcst(metadata_nodes)

    assert stimela_meta == {"dtype": "File", "must_exist": True}
    print("✓ Stimela metadata extracted correctly")


def test_extract_stimela_metadata_no_dict():
    """Test that missing stimela dict returns empty dict."""
    code = """
from typing import Annotated
import typer

def foo(
    param: Annotated[
        str,
        typer.Option(help="Test param"),
    ]
):
    pass
"""
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]

    from hip_cargo.utils.introspector import parse_annotated_libcst

    annotation_node = cst_param.annotation.annotation
    dtype_node, metadata_nodes = parse_annotated_libcst(annotation_node)

    stimela_meta = extract_stimela_metadata_libcst(metadata_nodes)

    assert stimela_meta == {}
    print("✓ Missing stimela dict returns empty dict")


def test_stimela_dtype_override():
    """Test that stimela dtype overrides type hint inference."""
    code = """
from pathlib import Path
from typing import Annotated, NewType
import typer

File = NewType("File", Path)

def foo(
    param: Annotated[
        str,
        typer.Option(help="Test param"),
        {"stimela": {"dtype": "File"}}
    ] = "default.txt"
):
    pass
"""
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]

    param_name, input_def = extract_input_libcst(cst_param)

    assert param_name == "param"
    assert input_def["dtype"] == "File"  # Should be File, not str
    assert input_def["default"] == "default.txt"
    print("✓ Stimela dtype overrides type hint inference")


def test_stimela_arbitrary_fields():
    """Test that arbitrary fields pass through."""
    code = """
from typing import Annotated
import typer

def foo(
    param: Annotated[
        str,
        typer.Option(help="Test"),
        {"stimela": {"custom_field": "custom_value", "another": 123, "nested": {"key": "value"}}}
    ] = "default"
):
    pass
"""
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]

    param_name, input_def = extract_input_libcst(cst_param)

    assert input_def["custom_field"] == "custom_value"
    assert input_def["another"] == 123
    assert input_def["nested"] == {"key": "value"}
    print("✓ Arbitrary fields pass through")


def test_stimela_policies_merge():
    """Test that stimela policies merge with inferred policies."""
    code = """
from pathlib import Path
from typing import Annotated, NewType
import typer

File = NewType("File", Path)

def foo(
    input_file: Annotated[
        File,
        typer.Option(..., parser=Path, help="Input file"),
        {"stimela": {"policies": {"skip": True, "io": "copy"}}}
    ]
):
    pass
"""
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]

    param_name, input_def = extract_input_libcst(cst_param)

    # Should have both inferred (positional) and explicit (skip, io) policies
    assert input_def["policies"]["positional"] is True  # Inferred from required
    assert input_def["policies"]["skip"] is True  # From stimela dict
    assert input_def["policies"]["io"] == "copy"  # From stimela dict
    print("✓ Policies merge correctly (inferred + explicit)")


def test_stimela_roundtrip():
    """Test CLI -> YAML -> CLI preserves stimela metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a CLI file with stimela metadata
        cli_dir = tmpdir / "src" / "test_pkg" / "cli"
        cli_dir.mkdir(parents=True)
        test_file = cli_dir / "test_stimela.py"

        test_code = '''from pathlib import Path
from typing import Annotated, NewType

import typer

from hip_cargo.utils.decorators import stimela_cab

File = NewType("File", Path)


@stimela_cab(
    name="test_stimela",
    info="Test stimela metadata.",
)
def test_stimela(
    input_file: Annotated[
        File,
        typer.Option(..., parser=Path, help="Input file"),
        {"stimela": {"must_exist": True, "policies": {"io": "copy"}}}
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option(parser=Path, help="Output directory"),
        {"stimela": {"dtype": "Directory", "mkdir": True}}
    ] = None,
):
    """Test command."""
    pass
'''
        test_file.write_text(test_code)

        print("=" * 60)
        print("STEP 1: CLI → CAB")
        print("=" * 60)

        # Generate cab
        generate_cabs([test_file], output_dir=tmpdir)

        # Check YAML has the metadata
        cab_file = tmpdir / "test_stimela.yml"
        with open(cab_file) as f:
            yaml_content = f.read()

        print(f"\nGenerated YAML:\n{yaml_content}")

        # Verify metadata in YAML
        assert "must_exist: true" in yaml_content
        assert "mkdir: true" in yaml_content
        assert "io: copy" in yaml_content
        print("✓ Stimela metadata present in YAML")

        print("\n" + "=" * 60)
        print("STEP 2: CAB → CLI")
        print("=" * 60)

        # Generate Python from cab
        gen_file = tmpdir / "test_stimela_generated.py"
        generate_function(cab_file=cab_file, output_file=gen_file, config_file=Path("pyproject.toml"))

        with open(gen_file) as f:
            python_code = f.read()

        print(f"\nGenerated Python:\n{python_code}")

        # Verify stimela dict in generated code (multi-line format with trailing commas)
        assert '"stimela":' in python_code or "'stimela':" in python_code
        assert "must_exist" in python_code
        assert "mkdir" in python_code
        assert "io" in python_code

        print("✓ Stimela metadata preserved in roundtrip")


def test_backward_compatibility():
    """Test that functions without stimela dict work as before."""
    code = """
from pathlib import Path
from typing import Annotated, NewType
import typer

File = NewType("File", Path)

def foo(
    input_file: Annotated[
        File,
        typer.Option(..., parser=Path, help="Input file"),
    ],
    output: Annotated[
        str | None,
        typer.Option(help="Output file"),
    ] = None,
):
    pass
"""
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]

    # First parameter (required File)
    cst_param1 = cst_func.params.params[0]
    param_name1, input_def1 = extract_input_libcst(cst_param1)

    assert param_name1 == "input_file"
    assert input_def1["dtype"] == "File"
    assert input_def1["required"] is True
    assert input_def1["policies"]["positional"] is True

    # Second parameter (optional str)
    cst_param2 = cst_func.params.params[1]
    param_name2, input_def2 = extract_input_libcst(cst_param2)

    assert param_name2 == "output"
    assert "dtype" not in input_def2  # str is default, not added
    # When default is None, it's not required but also doesn't have a default field
    # (None defaults are handled by the function signature itself)
    assert "required" not in input_def2 or input_def2.get("required") is False

    print("✓ Backward compatibility maintained")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Stimela Metadata Feature")
    print("=" * 60)

    test_extract_stimela_metadata_basic()
    test_extract_stimela_metadata_no_dict()
    test_stimela_dtype_override()
    test_stimela_arbitrary_fields()
    test_stimela_policies_merge()
    test_stimela_roundtrip()
    test_backward_compatibility()

    print("\n" + "=" * 60)
    print("✅ All Stimela Metadata Tests Passed!")
    print("=" * 60)
