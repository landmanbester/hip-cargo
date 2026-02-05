"""Test comment preservation in extract_input_libcst."""

import libcst as cst

from hip_cargo.utils.introspector import extract_input_libcst


def test_inline_comment_noqa_e501():
    """Test preserving # noqa: E501 inline comment."""
    code = """
from pathlib import Path
from typing import Annotated, NewType
import typer

Directory = NewType("Directory", Path)

def foo(
    output_dir: Annotated[
        Directory | None,
        typer.Option(
            parser=Path,
            help="Output directory for cab definition. "
            "The cab will have the exact same name as the command."  # noqa: E501
        ),
    ] = None
):
    pass
"""
    # Parse with LibCST
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]
    param_name, input_def = extract_input_libcst(cst_param)

    print(f"\nParameter: {param_name}")
    print(f"Info: {input_def.get('info')}")

    # Check that comment is preserved
    assert param_name == "output_dir"
    assert "info" in input_def
    assert "# noqa: E501" in input_def["info"]
    assert input_def["info"].endswith("# noqa: E501")

    print("✓ PASSED - # noqa: E501 comment preserved")


def test_inline_comment_type_ignore():
    """Test preserving # type: ignore inline comment."""
    code = """
from typing import Annotated
import typer

def foo(
    param: Annotated[
        str,
        typer.Option(
            help="Some parameter description"  # type: ignore
        ),
    ] = "default"
):
    pass
"""
    # Parse with LibCST
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]
    param_name, input_def = extract_input_libcst(cst_param)

    print(f"\nParameter: {param_name}")
    print(f"Info: {input_def.get('info')}")

    # Check that comment is preserved
    assert param_name == "param"
    assert "info" in input_def
    assert "# type: ignore" in input_def["info"]

    print("✓ PASSED - # type: ignore comment preserved")


def test_no_comment():
    """Test that parameters without comments work normally."""
    code = """
from typing import Annotated
import typer

def foo(
    param: Annotated[
        str,
        typer.Option(
            help="Some parameter description"
        ),
    ] = "default"
):
    pass
"""
    # Parse with LibCST
    cst_tree = cst.parse_module(code)
    cst_func = cst_tree.body[-1]
    cst_param = cst_func.params.params[0]
    param_name, input_def = extract_input_libcst(cst_param)

    print(f"\nParameter: {param_name}")
    print(f"Info: {input_def.get('info')}")

    # Check that there's no extra whitespace or artifacts
    assert param_name == "param"
    assert "info" in input_def
    assert input_def["info"] == "Some parameter description"
    assert "#" not in input_def["info"]

    print("✓ PASSED - No comment artifact")


def test_multiple_comment_types():
    """Test preserving various comment types."""
    test_cases = [
        ("# noqa: E501", "Line length check"),
        ("# type: ignore", "Type checking"),
        ("# pragma: no cover", "Coverage exclusion"),
        ("# pylint: disable=line-too-long", "Pylint directive"),
    ]

    for comment, description in test_cases:
        code = f"""
from typing import Annotated
import typer

def foo(
    param: Annotated[
        str,
        typer.Option(
            help="Test parameter"  {comment}
        ),
    ] = "default"
):
    pass
"""
        # Parse with LibCST
        cst_tree = cst.parse_module(code)
        cst_func = cst_tree.body[-1]
        cst_param = cst_func.params.params[0]
        param_name, input_def = extract_input_libcst(cst_param)

        print(f"\nTesting: {description} ({comment})")
        print(f"Info: {input_def.get('info')}")

        # Check that comment is preserved
        assert comment in input_def["info"], f"Comment '{comment}' not found in: {input_def['info']}"
        print(f"✓ PASSED - {comment} preserved")


if __name__ == "__main__":
    print("=" * 60)
    print("TESTING: Comment Preservation")
    print("=" * 60)

    test_inline_comment_noqa_e501()
    test_inline_comment_type_ignore()
    test_no_comment()
    test_multiple_comment_types()

    print("\n" + "=" * 60)
    print("✅ All comment preservation tests passed!")
    print("=" * 60)
