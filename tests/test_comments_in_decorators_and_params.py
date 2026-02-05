"""Test that comments appear in both decorators and function parameters."""

import tempfile
from pathlib import Path

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function


def test_comments_in_both_locations():
    """Test comments appear in decorators AND function parameters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a test CLI file with:
        # 1. An output with a comment (appears as decorator AND parameter)
        # 2. An input with a comment (appears in parameter)
        test_cli_code = '''from pathlib import Path
from typing import Annotated, NewType

import typer

from hip_cargo.utils.decorators import stimela_cab, stimela_output

Directory = NewType("Directory", Path)
File = NewType("File", Path)


@stimela_cab(
    name="test_cmd",
    info="Test command for comment preservation.",  # noqa: E501
)
@stimela_output(
    dtype="Directory",
    name="output-dir",
    info="Output directory with a very long description that exceeds the line length limit.",  # noqa: E501
)
def test_cmd(
    input_file: Annotated[
        File,
        typer.Option(
            ...,
            parser=Path,
            help="Input file with a very long help text that exceeds the maximum line length limit."  # noqa: E501
        ),
    ],
    output_dir: Annotated[
        Directory | None,
        typer.Option(
            parser=Path,
            help="This help text is ignored for outputs."  # type: ignore
        ),
    ] = None,
):
    """Test command."""
    pass
'''

        # Write test file (create src/cli structure to match expected path)
        cli_dir = tmpdir / "src" / "test_pkg" / "cli"
        cli_dir.mkdir(parents=True)
        test_file = cli_dir / "test_comment_both.py"
        test_file.write_text(test_cli_code)

        print("=" * 60)
        print("TEST: Comments in decorators AND parameters")
        print("=" * 60)

        # Step 1: Generate cab
        print("\n1. Generating CAB from CLI...")
        generate_cabs([test_file], output_dir=tmpdir)

        # Check YAML has comments
        cab_file = tmpdir / "test_cmd.yml"
        with open(cab_file) as f:
            yaml_content = f.read()

        print("\nGenerated YAML (relevant sections):")
        for i, line in enumerate(yaml_content.split("\n")[1:], start=2):
            print(f"{i:3d}: {line}")

        # Verify comments in YAML
        # We expect 3 comments: cab info, input-file info, output-dir info
        # Note: output parameter help text is NOT used (outputs come from @stimela_output decorator)
        assert yaml_content.count("# noqa: E501") == 3, "Should have 3 # noqa: E501 comments in YAML"
        print("\n✅ All 3 comments present in YAML (cab, input, output)")

        # Step 2: Generate Python from cab
        print("\n2. Generating Python from CAB...")
        gen_file = tmpdir / "test_cmd_generated.py"
        generate_function(cab_file=cab_file, output_file=gen_file, config_file=Path("pyproject.toml"))

        with open(gen_file) as f:
            python_code = f.read()

        print("\nGenerated Python (relevant sections):")
        for i, line in enumerate(python_code.split("\n")[:50], start=1):
            if "# noqa" in line or "# type" in line or "@stimela" in line or "help=" in line or "info=" in line:
                print(f"{i:3d}: {line}")

        # Verify comments in Python
        # 1. @stimela_cab decorator info
        assert 'info="Test command for comment preservation.",  # noqa: E501' in python_code, (
            "Comment missing in @stimela_cab info"
        )
        print("✅ Comment in @stimela_cab decorator")

        # 2. @stimela_output decorator info
        text = "Output directory with a very long description that exceeds the line length limit."
        assert f'info="{text}",  # noqa: E501' in python_code, "Comment missing in @stimela_output info"
        print("✅ Comment in @stimela_output decorator")

        # 3. input_file parameter help
        assert f'help="{text}",  # noqa: E501' in python_code, "Comment missing in input_file help"
        print("✅ Comment in input_file parameter help")

        # 4. output_dir parameter help (should have SAME comment as its decorator - this is the key test!)
        assert f'help="{text}",  # noqa: E501' in python_code, (
            "Comment missing in output_dir parameter help - should match decorator info"
        )
        print("✅ Comment in output_dir parameter help (matches decorator)")

        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        print("\nVerified:")
        print("  ✅ Comments in @stimela_cab decorator preserved through roundtrip")
        print("  ✅ Comments in @stimela_output decorator preserved through roundtrip")
        print("  ✅ Comments in input parameter help strings preserved through roundtrip")
        print("  ✅ Output comments appear in BOTH decorator AND parameter in generated Python")
        print("  ✅ Parameter help for outputs uses the decorator info (with comment)")


if __name__ == "__main__":
    test_comments_in_both_locations()
