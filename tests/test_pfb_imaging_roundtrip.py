"""Test round-trip conversion for pfb-imaging CLI modules.

This test ensures that hip-cargo can correctly process real-world CLI
modules from the pfb-imaging package. It verifies that:
1. Cabs can be generated from pfb-imaging CLI modules
2. Functions can be regenerated from those cabs
3. The regenerated functions compile without errors
4. The regenerated function produces the same cab structure

Requires pfb-imaging to be installed (lightweight mode is sufficient):
    pip install pfb-imaging

Skipped automatically if pfb-imaging is not installed.
"""

import importlib
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

pfb_imaging = pytest.importorskip("pfb_imaging", reason="pfb-imaging package not installed")

from hip_cargo.core.generate_cabs import generate_cabs  # noqa: E402
from hip_cargo.core.generate_function import generate_function  # noqa: E402


def _find_pfb_paths() -> tuple[Path, Path, Path | None]:
    """Locate pfb-imaging CLI, cabs, and pyproject.toml via importlib.

    Returns:
        (cli_dir, cabs_dir, config_file) tuple. config_file may be None
        if pyproject.toml is not found (e.g. installed from wheel).
    """
    cli_mod = importlib.import_module("pfb_imaging.cli")
    cabs_mod = importlib.import_module("pfb_imaging.cabs")
    cli_dir = Path(cli_mod.__path__[0])
    cabs_dir = Path(cabs_mod.__path__[0])

    # pyproject.toml is two levels up from the package dir (src/pfb_imaging/ -> project root)
    # This works for editable installs and src-layout packages
    pkg_dir = Path(pfb_imaging.__path__[0])
    config_file = None
    for candidate in [pkg_dir.parent.parent / "pyproject.toml", pkg_dir.parent / "pyproject.toml"]:
        if candidate.is_file():
            config_file = candidate
            break

    return cli_dir, cabs_dir, config_file


def _get_image_name(cabs_dir: Path) -> str | None:
    """Extract the container image from the first cab YAML file found."""
    for cab_file in cabs_dir.glob("*.yml"):
        with open(cab_file) as f:
            data = yaml.safe_load(f)
        cabs = data.get("cabs", {})
        for cab_def in cabs.values():
            image = cab_def.get("image")
            if image:
                return image
    return None


PFB_CLI_DIR, PFB_CABS_DIR, PFB_CONFIG = _find_pfb_paths()
PFB_IMAGE_NAME = _get_image_name(PFB_CABS_DIR)

# Discover CLI modules dynamically from the installed package
CLI_MODULES = sorted(p.stem for p in PFB_CLI_DIR.glob("*.py") if p.stem != "__init__" and not p.stem.startswith("_"))


@pytest.mark.integration
@pytest.mark.parametrize("module_name", CLI_MODULES)
def test_pfb_imaging_roundtrip(module_name):
    """Test round-trip conversion for a pfb-imaging CLI module.

    1. Generate cab from CLI module
    2. Compare generated cab with the package's shipped cab
    3. Regenerate function from the shipped cab
    4. Verify the regenerated function compiles and matches the original line-for-line
    """
    original_file = PFB_CLI_DIR / f"{module_name}.py"
    original_cab_file = PFB_CABS_DIR / f"{module_name}.yml"

    if not original_file.exists():
        pytest.skip(f"CLI module {module_name}.py not found in pfb-imaging")
    if not original_cab_file.exists():
        pytest.skip(f"Cab file {module_name}.yml not found in pfb-imaging")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Mirror the src layout so hip-cargo's path parsing works
        cli_dir = tmpdir / "src" / "pfb_imaging" / "cli"
        cli_dir.mkdir(parents=True)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        copied_file = cli_dir / f"{module_name}.py"
        shutil.copy2(original_file, copied_file)

        # Step 1: Generate cab from CLI module
        try:
            generate_cabs(
                [copied_file],
                output_dir=cab_dir,
                image=PFB_IMAGE_NAME,
            )
        except Exception as e:
            pytest.fail(f"Failed to generate cab for {module_name}: {e}")

        cab_file = cab_dir / f"{module_name}.yml"
        assert cab_file.exists(), f"Cab file should be generated for {module_name}"

        # Step 2: Compare generated cab with the shipped cab
        with open(original_cab_file) as f:
            original_cab = yaml.safe_load(f)
        with open(cab_file) as f:
            generated_cab = yaml.safe_load(f)

        assert original_cab == generated_cab, f"Generated cab does not match shipped cab for {module_name}"

        # Step 3: Regenerate function from the shipped cab
        generated_file = tmpdir / f"{module_name}_regenerated.py"
        try:
            generate_function(
                original_cab_file,
                output_file=generated_file,
                config_file=PFB_CONFIG,
            )
        except Exception as e:
            pytest.fail(f"Failed to regenerate function for {module_name}: {e}")

        assert generated_file.exists(), f"Generated function should exist for {module_name}"
        generated_code = generated_file.read_text()

        # Step 4a: Verify generated function compiles
        try:
            compile(generated_code, str(generated_file), "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated code for {module_name} has syntax error: {e}")

        # Step 4b: Line-for-line comparison with original CLI module
        original_code = original_file.read_text()
        original_lines = original_code.splitlines()
        generated_lines = generated_code.splitlines()

        assert len(original_lines) == len(generated_lines), (
            f"Line count mismatch for {module_name}: "
            f"original has {len(original_lines)} lines, "
            f"generated has {len(generated_lines)} lines"
        )

        for i, (orig_line, gen_line) in enumerate(zip(original_lines, generated_lines), 1):
            assert orig_line == gen_line, (
                f"Line {i} differs for {module_name}:\n  Original:  {orig_line}\n  Generated: {gen_line}"
            )


@pytest.mark.integration
def test_pfb_imaging_all_modules_batch():
    """Test generating all pfb-imaging cabs in one batch via wildcard."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        cli_dir = tmpdir / "src" / "pfb_imaging" / "cli"
        cli_dir.mkdir(parents=True)
        cab_dir = tmpdir / "cabs"
        cab_dir.mkdir()

        # Copy all CLI modules
        for module_name in CLI_MODULES:
            original_file = PFB_CLI_DIR / f"{module_name}.py"
            if original_file.exists():
                shutil.copy2(original_file, cli_dir / f"{module_name}.py")

        # Generate all cabs using wildcard
        wildcard_path = cli_dir / "*"
        generate_cabs([wildcard_path], output_dir=cab_dir)

        # Verify all cabs were created
        for module_name in CLI_MODULES:
            cab_file = cab_dir / f"{module_name}.yml"
            assert cab_file.exists(), f"Cab file should be generated for {module_name}"

        cab_files = list(cab_dir.glob("*.yml"))
        assert len(cab_files) == len(CLI_MODULES), f"Expected {len(CLI_MODULES)} cab files, found {len(cab_files)}"
