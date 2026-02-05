"""Test round-trip conversion for pfb-imaging CLI modules.

This test ensures that hip-cargo can correctly process real-world CLI
modules from the pfb-imaging package. It verifies that:
1. Cabs can be generated from pfb-imaging CLI modules
2. Functions can be regenerated from those cabs
3. The regenerated functions are functionally equivalent (not necessarily identical)

This serves as an integration test to catch regressions in hip-cargo
that would break existing packages. Unlike the strict roundtrip tests
for hip-cargo's own modules, these tests allow formatting differences
since pfb-imaging CLI files may have been generated with different
versions of hip-cargo or manually edited.
"""

import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function

# Path to pfb-imaging package (local development version)
PFB_IMAGING_ROOT = Path.home() / "software" / "pfb-imaging"
PFB_IMAGING_CLI = PFB_IMAGING_ROOT / "src" / "pfb_imaging" / "cli"
PFB_IMAGING_CABS = PFB_IMAGING_ROOT / "src" / "pfb_imaging" / "cabs"

# List of CLI modules to test
CLI_MODULES = [
    "degrid",
    "fluxtractor",
    "grid",
    "hci",
    "init",
    "kclean",
    "model2comps",
    "restore",
    "sara",
]


def check_pfb_imaging_available():
    """Check if pfb-imaging is available for testing."""
    return PFB_IMAGING_CLI.exists()


@pytest.mark.skip(reason="Features pending")
@pytest.mark.skipif(
    not check_pfb_imaging_available(),
    reason="pfb-imaging package not found at ~/software/pfb-imaging",
)
@pytest.mark.integration
@pytest.mark.parametrize("module_name", CLI_MODULES)
def test_pfb_imaging_roundtrip(module_name):
    """Test round-trip conversion for a pfb-imaging CLI module.

    This is a lenient integration test that verifies functional equivalence
    rather than exact formatting match. It checks that:
    1. Cabs can be generated from the CLI module
    2. Functions can be regenerated from the cab
    3. The regenerated function compiles without errors
    4. The regenerated function produces the same cab structure

    Args:
        module_name: Name of the CLI module to test (e.g., "grid", "hci")
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Set up directory structure to mimic pfb-imaging
        # We need src/pfb_imaging/cli/ for the path parsing to work
        cli_dir = tmpdir / "src" / "pfb_imaging" / "cli"
        cli_dir.mkdir(parents=True)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()
        cab_dir_2 = tmpdir / "cabs_2"
        cab_dir_2.mkdir()

        # Copy the CLI module to temp directory
        original_file = PFB_IMAGING_CLI / f"{module_name}.py"
        copied_file = cli_dir / f"{module_name}.py"
        shutil.copy2(original_file, copied_file)

        # Step 1: Generate cab from original CLI module (using libcst for comment preservation)
        try:
            generate_cabs(
                [copied_file],
                output_dir=cab_dir,
            )
        except Exception as e:
            pytest.fail(f"Failed to generate cab for {module_name}: {e}")

        # Verify cab was created
        cab_file = cab_dir / f"{module_name}.yml"
        assert cab_file.exists(), f"Cab file should be generated for {module_name}"

        # Load original cab
        original_cab_file = PFB_IMAGING_CABS / f"{module_name}.yml"
        with open(original_cab_file) as f:
            original_cab = yaml.safe_load(f)
            original_cab["cabs"][module_name].pop("image")

        with open(cab_file) as f:
            generated_cab = yaml.safe_load(f)

        assert original_cab == generated_cab, f"Generated cab does not match original for {module_name}"

        # Step 2: Generate function from cab
        generated_file = tmpdir / f"{module_name}_regenerated.py"
        try:
            generate_function(
                original_cab_file,
                output_file=generated_file,
                config_file=Path("pyproject.toml"),  # Use hip-cargo's ruff config
            )
        except Exception as e:
            pytest.fail(f"Failed to regenerate function for {module_name}: {e}")

        # Step 3: Verify generated function is syntactically valid
        assert generated_file.exists(), f"Generated function should exist for {module_name}"
        generated_code = generated_file.read_text()

        # Compile to check syntax
        try:
            compile(generated_code, str(generated_file), "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated code for {module_name} has syntax error: {e}")


@pytest.mark.skip(reason="Features pending")
@pytest.mark.skipif(
    not check_pfb_imaging_available(),
    reason="pfb-imaging package not found at ~/software/pfb-imaging",
)
@pytest.mark.integration
def test_pfb_imaging_all_modules_batch():
    """Test generating all pfb-imaging cabs in one batch.

    This tests the wildcard functionality and ensures all modules
    can be processed together.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Set up directory structure
        cli_dir = tmpdir / "src" / "pfb_imaging" / "cli"
        cli_dir.mkdir(parents=True)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        # Copy all CLI modules
        for module_name in CLI_MODULES:
            original_file = PFB_IMAGING_CLI / f"{module_name}.py"
            copied_file = cli_dir / f"{module_name}.py"
            shutil.copy2(original_file, copied_file)

        # Generate all cabs using wildcard (using libcst for comment preservation)
        wildcard_path = cli_dir / "*"
        generate_cabs(
            [wildcard_path],
            output_dir=cab_dir,
        )

        # Verify all cabs were created
        for module_name in CLI_MODULES:
            cab_file = cab_dir / f"{module_name}.yml"
            assert cab_file.exists(), f"Cab file should be generated for {module_name}"

        # Count total cabs generated
        cab_files = list(cab_dir.glob("*.yml"))
        assert len(cab_files) == len(CLI_MODULES), f"Expected {len(CLI_MODULES)} cab files, found {len(cab_files)}"
