"""Test round-trip conversion: CLI function -> cab -> function."""

import re
import tempfile
from pathlib import Path

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function


def test_roundtrip_generate_cabs():
    """Test round-trip: generate_cabs CLI -> cab -> generated function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        # Step 1: Generate cabs from CLI module (using libcst for comment preservation)
        cli_module = Path("src/hip_cargo/cli/generate_cabs.py")
        generate_cabs(
            [cli_module],
            output_dir=cab_dir,
        )

        # Step 2: Generate function from cab
        cab_file = cab_dir / "generate_cabs.yml"
        assert cab_file.exists(), "Cab file should be generated"

        generated_file = tmpdir / "generate_cabs_roundtrip.py"
        generate_function(cab_file, output_file=generated_file, config_file=Path("pyproject.toml"))

        # Step 3: Verify generated function is syntactically valid
        assert generated_file.exists(), "Generated function should exist"
        generated_code = generated_file.read_text()

        # Compile to check syntax
        compile(generated_code, str(generated_file), "exec")

        # Step 4: Compare with original (both should have been formatted with ruff)
        original_code = cli_module.read_text()

        # Compare line by line
        original_lines = original_code.splitlines()
        generated_lines = generated_code.splitlines()

        # They should match exactly after normalization
        assert len(original_lines) == len(generated_lines), (
            f"Line count mismatch: original has {len(original_lines)} lines, generated has {len(generated_lines)} lines"
        )

        for i, (orig_line, gen_line) in enumerate(zip(original_lines, generated_lines), 1):
            assert orig_line == gen_line, f"Line {i} differs:\n  Original:  {orig_line}\n  Generated: {gen_line}"


def test_roundtrip_generate_function():
    """Test round-trip: generate_function CLI -> cab -> generated function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        # Step 1: Generate cabs from CLI module (using libcst for comment preservation)
        cli_module = Path("src/hip_cargo/cli/generate_function.py")
        generate_cabs(
            [cli_module],
            output_dir=cab_dir,
        )

        # Step 2: Generate function from cab
        cab_file = cab_dir / "generate_function.yml"
        assert cab_file.exists(), "Cab file should be generated"

        generated_file = tmpdir / "generate_function_roundtrip.py"
        generate_function(cab_file, output_file=generated_file, config_file=Path("pyproject.toml"))

        # Step 3: Verify generated function is syntactically valid
        assert generated_file.exists(), "Generated function should exist"
        generated_code = generated_file.read_text()

        # Compile to check syntax
        compile(generated_code, str(generated_file), "exec")

        # Step 4: Compare with original (both should have been formatted with ruff)
        original_code = cli_module.read_text()

        # Compare line by line
        original_lines = original_code.splitlines()
        generated_lines = generated_code.splitlines()

        # They should match exactly after normalization
        assert len(original_lines) == len(generated_lines), (
            f"Line count mismatch: original has {len(original_lines)} lines, generated has {len(generated_lines)} lines"
        )
        for i, (orig_line, gen_line) in enumerate(zip(original_lines, generated_lines), 1):
            assert orig_line == gen_line, f"Line {i} differs:\n  Original:  {orig_line}\n  Generated: {gen_line}"


def test_roundtrip_preserves_spacing():
    """Test that round-trip preserves proper spacing in help strings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        # Generate cab from CLI (using libcst for comment preservation)
        cli_module = Path("src/hip_cargo/cli/generate_cabs.py")
        generate_cabs(
            [cli_module],
            output_dir=cab_dir,
        )

        # Generate function from cab
        cab_file = cab_dir / "generate_cabs.yml"
        generated_file = tmpdir / "test_spacing.py"
        generate_function(cab_file, output_file=generated_file, config_file=None)

        generated_code = generated_file.read_text()

        # Extract only info and help strings to check for proper spacing
        # Use regex to find help="..." and info="..." patterns (including multi-line strings)
        info_help_pattern = r'(?:help|info)=(?:"([^"]*)"|\'([^\']*)\'|"""(.*?)"""|\'\'\'(.*?)\'\'\')'
        matches = re.findall(info_help_pattern, generated_code, re.DOTALL)

        # Flatten matches (each match is a tuple with one non-empty group)
        info_help_strings = []
        for match_tuple in matches:
            for match_str in match_tuple:
                if match_str:
                    info_help_strings.append(match_str)

        # Check each info/help string for proper spacing after periods
        for info_str in info_help_strings:
            # Check for period followed by non-space character (but allow period at end of string)
            # Also allow period followed by newline
            bad_spacing = re.search(r"\.[^\s\n]", info_str)
            assert not bad_spacing, (
                f"Info/help string has improper spacing after period:\n"
                f"  String: {info_str!r}\n"
                f"  Bad pattern at position {bad_spacing.start() if bad_spacing else 'N/A'}"
            )
