"""Integration tests for the container fallback code generation and execution path.

Tests the full flow: cab YAML with image → generate function → verify generated code
compiles and the fallback pattern works correctly when dependencies are missing.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from hip_cargo.core.generate_function import generate_function


def _write_cab_with_image(cab_dir: Path) -> Path:
    """Write a minimal cab YAML with an image field for testing."""
    cab = {
        "cabs": {
            "process-data": {
                "info": "Process input data",
                "flavour": "python",
                "command": "my_pkg.core.process_data.process_data",
                "image": "ghcr.io/user/my-pkg:latest",
                "inputs": {
                    "input-ms": {
                        "dtype": "MS",
                        "required": True,
                        "info": "Input measurement set",
                        "policies": {"positional": True},
                    },
                    "threshold": {
                        "dtype": "float",
                        "default": 0.5,
                        "info": "Threshold value",
                    },
                },
                "outputs": {
                    "output-dir": {
                        "dtype": "Directory",
                        "info": "Output directory",
                    },
                },
            }
        }
    }
    cab_file = cab_dir / "process_data.yml"
    with open(cab_file, "w") as f:
        yaml.safe_dump(cab, f, sort_keys=False)
    return cab_file


def _write_cab_without_image(cab_dir: Path) -> Path:
    """Write a minimal cab YAML without an image field."""
    cab = {
        "cabs": {
            "simple-task": {
                "info": "Simple task",
                "flavour": "python",
                "command": "my_pkg.core.simple_task.simple_task",
                "inputs": {
                    "name": {
                        "dtype": "str",
                        "required": True,
                        "info": "Name",
                        "policies": {"positional": True},
                    },
                },
                "outputs": {},
            }
        }
    }
    cab_file = cab_dir / "simple_task.yml"
    with open(cab_file, "w") as f:
        yaml.safe_dump(cab, f, sort_keys=False)
    return cab_file


class TestGeneratedFallbackCodeStructure:
    """Verify the generated Python code has correct container fallback structure."""

    @pytest.mark.integration
    def test_generated_code_with_image_compiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_file = _write_cab_with_image(tmpdir)
            output_file = tmpdir / "process_data.py"
            generate_function(cab_file, output_file=output_file)

            code = output_file.read_text()
            compile(code, str(output_file), "exec")

    @pytest.mark.integration
    def test_generated_code_contains_fallback_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_file = _write_cab_with_image(tmpdir)
            output_file = tmpdir / "process_data.py"
            generate_function(cab_file, output_file=output_file)

            code = output_file.read_text()

            # Verify the try/except ImportError pattern
            # ruff may normalize quotes to double quotes
            assert 'if backend == "native" or backend == "auto":' in code
            assert "try:" in code
            assert "except ImportError:" in code
            assert 'if backend == "native":' in code

            # Verify container fallback imports
            assert "from hip_cargo.utils.config import get_container_image" in code
            assert "from hip_cargo.utils.runner import run_in_container" in code

            # Verify backend and always_pull_images parameters exist
            assert "backend" in code
            assert "always_pull_images" in code

    @pytest.mark.integration
    def test_generated_code_without_image_has_no_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_file = _write_cab_without_image(tmpdir)
            output_file = tmpdir / "simple_task.py"
            generate_function(cab_file, output_file=output_file)

            code = output_file.read_text()
            compile(code, str(output_file), "exec")

            assert "ImportError" not in code
            assert "run_in_container" not in code
            assert "get_container_image" not in code

    @pytest.mark.integration
    def test_generated_code_has_backend_param_only_with_image(self):
        """backend and always_pull_images should only appear when cab has image."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # With image
            cab_file = _write_cab_with_image(tmpdir)
            output_with = tmpdir / "with_image.py"
            generate_function(cab_file, output_file=output_with)
            code_with = output_with.read_text()
            assert "backend:" in code_with or "backend =" in code_with or "backend='" in code_with

            # Without image
            cab_file = _write_cab_without_image(tmpdir)
            output_without = tmpdir / "without_image.py"
            generate_function(cab_file, output_file=output_without)
            code_without = output_without.read_text()
            assert "always_pull_images" not in code_without


class TestFallbackExecutionPath:
    """Test the actual execution behavior of the generated fallback code."""

    @pytest.mark.integration
    def test_native_import_success_calls_core(self):
        """When core module is importable, it should be called directly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_file = _write_cab_with_image(tmpdir)
            output_file = tmpdir / "process_data.py"
            generate_function(cab_file, output_file=output_file)

            code = output_file.read_text()

            # Create a mock core module
            mock_core = MagicMock()
            mock_module = MagicMock()
            mock_module.process_data = mock_core

            # Execute the generated code with mocked imports
            namespace = {}
            exec(compile(code, str(output_file), "exec"), namespace)
            func = namespace["process_data"]

            with patch.dict(
                "sys.modules",
                {
                    "my_pkg": MagicMock(),
                    "my_pkg.core": MagicMock(),
                    "my_pkg.core.process_data": mock_module,
                },
            ):
                func(
                    input_ms=Path("/data/input.ms"),
                    threshold=0.5,
                    output_dir=Path("/output"),
                    backend="auto",
                    always_pull_images=False,
                )

            mock_core.assert_called_once()

    @pytest.mark.integration
    def test_import_error_triggers_container_fallback(self):
        """When core import fails, should fall back to container execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_file = _write_cab_with_image(tmpdir)
            output_file = tmpdir / "process_data.py"
            generate_function(cab_file, output_file=output_file)

            code = output_file.read_text()

            namespace = {}
            exec(compile(code, str(output_file), "exec"), namespace)
            func = namespace["process_data"]

            mock_run = MagicMock()
            mock_get_image = MagicMock(return_value="ghcr.io/user/my-pkg:latest")

            # Patch the lazy import to raise ImportError, and mock the fallback
            with (
                patch.dict(
                    "sys.modules",
                    {
                        "my_pkg": None,  # causes ImportError
                    },
                ),
                patch("hip_cargo.utils.config.get_container_image", mock_get_image),
                patch("hip_cargo.utils.runner.run_in_container", mock_run),
            ):
                func(
                    input_ms=Path("/data/input.ms"),
                    threshold=0.5,
                    output_dir=Path("/output"),
                    backend="auto",
                    always_pull_images=False,
                )

            mock_get_image.assert_called_once_with("my-pkg")
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args
            assert call_kwargs[1]["image"] == "ghcr.io/user/my-pkg:latest"
            assert call_kwargs[1]["backend"] == "auto"

    @pytest.mark.integration
    def test_native_backend_reraises_import_error(self):
        """With backend='native', ImportError should propagate instead of falling back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_file = _write_cab_with_image(tmpdir)
            output_file = tmpdir / "process_data.py"
            generate_function(cab_file, output_file=output_file)

            code = output_file.read_text()

            namespace = {}
            exec(compile(code, str(output_file), "exec"), namespace)
            func = namespace["process_data"]

            with (
                patch.dict("sys.modules", {"my_pkg": None}),
                pytest.raises(ImportError),
            ):
                func(
                    input_ms=Path("/data/input.ms"),
                    backend="native",
                    always_pull_images=False,
                )

    @pytest.mark.integration
    def test_no_container_url_raises_runtime_error(self):
        """When get_container_image returns None, should raise RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_file = _write_cab_with_image(tmpdir)
            output_file = tmpdir / "process_data.py"
            generate_function(cab_file, output_file=output_file)

            code = output_file.read_text()

            namespace = {}
            exec(compile(code, str(output_file), "exec"), namespace)
            func = namespace["process_data"]

            mock_get_image = MagicMock(return_value=None)

            with (
                patch.dict("sys.modules", {"my_pkg": None}),
                patch("hip_cargo.utils.config.get_container_image", mock_get_image),
                pytest.raises(RuntimeError, match="No Container URL"),
            ):
                func(
                    input_ms=Path("/data/input.ms"),
                    backend="auto",
                    always_pull_images=False,
                )


class TestGenerateCabsImageResolution:
    """Test that generate_cabs resolves image from package metadata."""

    @pytest.mark.integration
    def test_generate_cabs_resolves_image_from_metadata(self):
        """generate_cabs should resolve image from hip-cargo's own metadata."""
        from hip_cargo.core.generate_cabs import generate_cabs

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_dir = tmpdir / "cabs"
            cab_dir.mkdir()

            cli_module = Path("src/hip_cargo/cli/generate_cabs.py")
            generate_cabs([cli_module], output_dir=cab_dir)

            cab_file = cab_dir / "generate_cabs.yml"
            assert cab_file.exists()

            with open(cab_file) as f:
                data = yaml.safe_load(f)

            cab_def = data["cabs"]["generate_cabs"]
            # hip-cargo has a Container URL, so image should be present
            assert "image" in cab_def
            assert "ghcr.io/" in cab_def["image"]

    @pytest.mark.integration
    def test_generate_cabs_image_override(self):
        """--image flag should override resolved image."""
        from hip_cargo.core.generate_cabs import generate_cabs

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            cab_dir = tmpdir / "cabs"
            cab_dir.mkdir()

            cli_module = Path("src/hip_cargo/cli/generate_cabs.py")
            generate_cabs(
                [cli_module],
                output_dir=cab_dir,
                image="custom.registry.io/team/pkg:v2.0",
            )

            cab_file = cab_dir / "generate_cabs.yml"
            with open(cab_file) as f:
                data = yaml.safe_load(f)

            cab_def = data["cabs"]["generate_cabs"]
            assert cab_def["image"] == "custom.registry.io/team/pkg:v2.0"
