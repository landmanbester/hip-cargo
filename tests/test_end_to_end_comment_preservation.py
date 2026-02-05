"""End-to-end test for comment preservation in generate-cabs."""

import tempfile
from pathlib import Path

from hip_cargo.core.generate_cabs import generate_cabs


def test_comment_preservation_in_real_file():
    """Test that comments are preserved in the actual generate_cabs.py file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Generate the cab
        cli_file = Path("src/hip_cargo/cli/generate_cabs.py")
        output_dir = tmpdir

        generate_cabs([cli_file], output_dir=output_dir)

        # Read the generated YAML
        yaml_file = output_dir / "generate_cabs.yml"
        with open(yaml_file, "r") as f:
            content = f.read()

        print("=" * 60)
        print("Full YAML content:")
        print("=" * 60)
        print(content)
        print("=" * 60)

        # Verify comment is preserved as a YAML comment (not in parsed data)
        # Comments are stripped by yaml.safe_load(), so check raw content
        assert "# noqa: E501" in content, "Comment '# noqa: E501' not found in YAML"

        # Also verify it's on the correct line (after the command text)
        lines = content.split("\n")
        found_comment_line = False
        for line in lines:
            if "The cab will have the exact same name as the command" in line and "# noqa: E501" in line:
                found_comment_line = True
                print(f"✅ SUCCESS: Comment found on correct line: {line.strip()}")
                break

        assert found_comment_line, "Comment not found on the expected line"


if __name__ == "__main__":
    test_comment_preservation_in_real_file()
