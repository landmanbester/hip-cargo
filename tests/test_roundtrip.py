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
        generate_function(cab_file, output_file=generated_file, config_file=None)

        generated_code = generated_file.read_text()

        # Assert that there are no occurrences of a period immediately followed
        # by a non-space character (except for newline)
        assert not re.search(r"\.\S", generated_code), "Multi-line strings should have a space after periods"
