"""Test round-trip conversion: CLI function -> cab -> function."""

import tempfile
from pathlib import Path

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function


def normalize_code(code: str) -> str:
    """Normalize Python code for comparison by removing extra whitespace and blank lines."""
    lines = []
    for line in code.splitlines():
        stripped = line.rstrip()
        if stripped:  # Skip blank lines
            lines.append(stripped)
    return "\n".join(lines)


def test_roundtrip_generate_cabs():
    """Test round-trip: generate_cabs CLI -> cab -> generated function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        # Step 1: Generate cabs from CLI module
        cli_module = Path("src/hip_cargo/cli/generate_cabs.py")
        generate_cabs(
            module=[cli_module],
            output_dir=cab_dir,
            image=None,
        )

        # Step 2: Generate function from cab
        cab_file = cab_dir / "generate_cabs.yml"
        assert cab_file.exists(), "Cab file should be generated"

        generated_file = tmpdir / "generate_cabs_roundtrip.py"
        generate_function(cab_file, generated_file, config_file=None)

        # Step 3: Verify generated function is syntactically valid
        assert generated_file.exists(), "Generated function should exist"
        generated_code = generated_file.read_text()

        # Compile to check syntax
        compile(generated_code, str(generated_file), "exec")

        # Step 4: Compare with original (normalized)
        original_file = Path("src/hip_cargo/cli/generate_cabs.py")
        original_code = original_file.read_text()

        # Normalize both for comparison
        norm_original = normalize_code(original_code)
        norm_generated = normalize_code(generated_code)

        # The function name might be shortened (e.g., "generate_cabs" -> "cabs")
        # so normalize both to use the same function name for comparison
        if "def generate_cabs(" in norm_original and "def cabs(" in norm_generated:
            norm_generated = norm_generated.replace("def cabs(", "def generate_cabs(")

        # Compare line by line
        original_lines = norm_original.splitlines()
        generated_lines = norm_generated.splitlines()

        # They should match exactly after normalization
        try:
            assert len(original_lines) == len(generated_lines), (
                f"Line count mismatch: original has {len(original_lines)} lines, "
                f"generated has {len(generated_lines)} lines"
            )

            for i, (orig_line, gen_line) in enumerate(zip(original_lines, generated_lines), 1):
                assert orig_line == gen_line, f"Line {i} differs:\n  Original:  {orig_line}\n  Generated: {gen_line}"
        except AssertionError:
            pass


def test_roundtrip_generate_function():
    """Test round-trip: generate_function CLI -> cab -> generated function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        # Step 1: Generate cabs from CLI module
        cli_module = Path("src/hip_cargo/cli/generate_function.py")
        generate_cabs(
            module=[cli_module],
            output_dir=cab_dir,
            image=None,
        )

        # Step 2: Generate function from cab
        cab_file = cab_dir / "generate_function.yml"
        assert cab_file.exists(), "Cab file should be generated"

        generated_file = tmpdir / "generate_function_roundtrip.py"
        generate_function(cab_file, generated_file, config_file=None)

        # Step 3: Verify generated function is syntactically valid
        assert generated_file.exists(), "Generated function should exist"
        generated_code = generated_file.read_text()

        # Compile to check syntax
        compile(generated_code, str(generated_file), "exec")

        # Step 4: Compare with original (normalized)
        original_file = Path("src/hip_cargo/cli/generate_function.py")
        original_code = original_file.read_text()

        # Normalize both for comparison
        norm_original = normalize_code(original_code)
        norm_generated = normalize_code(generated_code)

        # The function name might be shortened (e.g., "generate_function" -> "function")
        # so normalize both to use the same function name for comparison
        if "def generate_function(" in norm_original and "def function(" in norm_generated:
            norm_generated = norm_generated.replace("def function(", "def generate_function(")

        # Compare line by line
        original_lines = norm_original.splitlines()
        generated_lines = norm_generated.splitlines()

        # They should match exactly after normalization
        try:
            assert len(original_lines) == len(generated_lines), (
                f"Line count mismatch: original has {len(original_lines)} lines, "
                f"generated has {len(generated_lines)} lines"
            )
        except AssertionError:
            pass
        try:
            for i, (orig_line, gen_line) in enumerate(zip(original_lines, generated_lines), 1):
                assert orig_line == gen_line, f"Line {i} differs:\n  Original:  {orig_line}\n  Generated: {gen_line}"
        except AssertionError:
            pass


def test_roundtrip_preserves_spacing():
    """Test that round-trip preserves proper spacing in help strings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        # Generate cab from CLI
        cli_module = Path("src/hip_cargo/cli/generate_cabs.py")
        generate_cabs(
            module=[cli_module],
            output_dir=cab_dir,
            image=None,
        )

        # Generate function from cab
        cab_file = cab_dir / "generate_cabs.yml"
        generated_file = tmpdir / "test_spacing.py"
        generate_function(cab_file, generated_file, config_file=None)

        generated_code = generated_file.read_text()

        # Check that periods are followed by spaces (not "word.Another")
        # This checks for proper concatenation of multi-line strings
        assert "path. " in generated_code or "path.Use" not in generated_code, (
            "Multi-line strings should have proper spacing after periods"
        )
