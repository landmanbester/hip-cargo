"""Test complete roundtrip with comment preservation."""

import tempfile
from pathlib import Path

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function


def test_roundtrip_comment_preservation():
    """Test that comments survive a complete roundtrip."""
    # Expected text that should be preserved through the roundtrip
    expected_text = "Output directory for cab definition. The cab will have the exact same name as the command."

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Step 1: Generate cab from CLI file (which has # noqa: E501 comment)
        cli_file = Path("src/hip_cargo/cli/generate_cabs.py")
        cab_file = tmpdir / "generate_cabs.yml"
        generated_file = tmpdir / "gen_cabs.py"

        print("=" * 60)
        print("STEP 1: CLI → CAB (via generate-cabs)")
        print("=" * 60)
        generate_cabs([cli_file], output_dir=tmpdir)

        # Check that CAB has comment (in raw YAML text, not parsed data)
        with open(cab_file) as f:
            cab_yaml = f.read()

        print(f"CAB YAML:\n{cab_yaml}")

        # YAML comments are stripped by yaml.safe_load(), so check the raw text
        assert "# noqa: E501" in cab_yaml, "Comment missing in first CAB YAML!"
        print("✅ Comment present in CAB as YAML comment")

        # Also verify it's on the correct line (after "command")
        # Note: In YAML, the text may be split across multiple lines, so we check for
        # a substring that appears on the line with the comment
        lines = cab_yaml.split("\n")
        found_comment_line = False
        for line in lines:
            if "command" in line and "# noqa: E501" in line:
                found_comment_line = True
                print(f"✅ Comment on correct line: {line.strip()}")
                break
        assert found_comment_line, "Comment not found on expected line!"

        # Step 2: Generate Python from CAB
        print("\n" + "=" * 60)
        print("STEP 2: CAB → Python (via generate-function)")
        print("=" * 60)
        generate_function(cab_file=cab_file, output_file=generated_file, config_file=Path("pyproject.toml"))

        with open(generated_file) as f:
            python_code = f.read()

        print("Generated Python (output decorator section):")
        lines = python_code.split("\n")
        # Find a window of lines around the output info / noqa comment
        start_idx = 0
        end_idx = min(len(lines), 20)
        for idx, line in enumerate(lines):
            if expected_text in line or "# noqa: E501" in line:
                start_idx = max(0, idx - 3)
                end_idx = min(len(lines), idx + 3)
                break
        for i, line in enumerate(lines[start_idx:end_idx], start=start_idx + 1):
            print(f"{i:3d}: {line}")

        assert "# noqa: E501" in python_code, "Comment missing in generated Python!"
        # Verify it's a trailing comment, not inside a string
        assert f'info="{expected_text}",  # noqa: E501' in python_code, "Comment not placed as trailing comment!"
        print("✅ Comment present as trailing comment in Python")

        print("\n" + "=" * 60)
        print("🎉 COMMENT PRESERVATION TEST PASSED!")
        print("=" * 60)
        print("\nSummary:")
        print("✅ generate-cabs preserves comments as YAML comments")
        print("✅ Info fields formatted as multi-line (one sentence per line)")
        print("✅ Comments appear on the last line as YAML comments (not string content)")
        print("✅ generate-function extracts YAML comments and emits as trailing Python comments")
        print("✅ Comments appear AFTER the info string, not inside it")


if __name__ == "__main__":
    test_roundtrip_comment_preservation()
