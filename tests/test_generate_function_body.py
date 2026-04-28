"""Tests for generate_function_body in cab_to_function.py.

Verifies the generated code patterns: simple lazy import (no image) vs
try/except ImportError with container fallback (image present).
"""

import pytest

from hip_cargo.utils.cab_to_function import generate_function_body


class TestGenerateFunctionBodyNoImage:
    """When cab has no image, generate simple lazy import pattern."""

    @pytest.mark.unit
    def test_simple_lazy_import(self):
        cab_def = {"command": "my_pkg.core.process.process", "_name": "process"}
        inputs = {"input-file": {"dtype": "File", "required": True}}
        outputs = {}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        assert "from my_pkg.core.process import process as process_core" in code
        assert "process_core(" in code
        assert "input_file," in code
        # No container fallback
        assert "ImportError" not in code
        assert "run_in_container" not in code
        assert "get_container_image" not in code

    @pytest.mark.unit
    def test_no_image_indentation(self):
        """Without image, code should be at 4-space indentation (function body level)."""
        cab_def = {"command": "pkg.core.run.run", "_name": "run"}
        inputs = {"threshold": {"dtype": "float", "required": False}}
        outputs = {}

        lines = generate_function_body(cab_def, inputs, outputs)
        # Lines with content should start with 4 spaces (not 12)
        content_lines = [line for line in lines if line.strip()]
        for line in content_lines:
            assert line.startswith("    "), f"Expected 4-space indent: {line!r}"
            assert not line.startswith("        try:"), "Should not have try block"


class TestGenerateFunctionBodyWithImage:
    """When cab has an image, generate try/except ImportError with container fallback."""

    @pytest.mark.unit
    def test_try_except_import_error(self):
        cab_def = {
            "command": "pfb_imaging.core.grid.grid",
            "image": "ghcr.io/user/pfb-imaging:latest",
            "_name": "grid",
        }
        inputs = {"ms": {"dtype": "MS", "required": True}}
        outputs = {"output-dir": {"dtype": "Directory", "policies": {}}}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        assert "if backend == 'native' or backend == 'auto':" in code
        assert "try:" in code
        assert "except ImportError:" in code

    @pytest.mark.unit
    def test_native_backend_reraises(self):
        cab_def = {
            "command": "pfb_imaging.core.grid.grid",
            "image": "ghcr.io/user/pfb-imaging:latest",
            "_name": "grid",
        }
        inputs = {}
        outputs = {}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        assert "if backend == 'native':" in code
        assert "raise" in code

    @pytest.mark.unit
    def test_container_fallback_imports(self):
        cab_def = {
            "command": "pfb_imaging.core.grid.grid",
            "image": "ghcr.io/user/pfb-imaging:latest",
            "_name": "grid",
        }
        inputs = {}
        outputs = {}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        assert "from hip_cargo.utils.config import get_container_image" in code
        assert "from hip_cargo.utils.runner import run_in_container" in code

    @pytest.mark.unit
    def test_distribution_name_derived_from_command(self):
        """Distribution name should be derived from command's top-level package."""
        cab_def = {
            "command": "pfb_imaging.core.grid.grid",
            "image": "ghcr.io/user/pfb-imaging:latest",
            "_name": "grid",
        }
        inputs = {}
        outputs = {}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        # pfb_imaging → pfb-imaging
        assert 'get_container_image("pfb-imaging")' in code

    @pytest.mark.unit
    def test_runtime_error_on_no_image(self):
        """Should raise RuntimeError if get_container_image returns None."""
        cab_def = {
            "command": "pfb_imaging.core.grid.grid",
            "image": "ghcr.io/user/pfb-imaging:latest",
            "_name": "grid",
        }
        inputs = {}
        outputs = {}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        assert "if image is None:" in code
        assert "RuntimeError" in code

    @pytest.mark.unit
    def test_run_in_container_call(self):
        cab_def = {
            "command": "pfb_imaging.core.grid.grid",
            "image": "ghcr.io/user/pfb-imaging:latest",
            "_name": "grid",
        }
        inputs = {"ms": {"dtype": "MS", "required": True}}
        outputs = {"output-dir": {"dtype": "Directory", "policies": {}}}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        assert "run_in_container(" in code
        assert "grid," in code  # func reference
        assert "image=image," in code
        assert "backend=backend," in code
        assert "always_pull_images=always_pull_images," in code
        # Params dict should include both inputs and outputs
        assert "ms=ms," in code
        assert "output_dir=output_dir," in code

    @pytest.mark.unit
    def test_params_ordering_positional_then_keyword(self):
        """Required params should appear before optional params in the core call."""
        cab_def = {
            "command": "pkg.core.run.run",
            "image": "ghcr.io/user/pkg:latest",
            "_name": "run",
        }
        inputs = {
            "required-param": {"dtype": "str", "required": True},
            "optional-param": {"dtype": "int", "required": False},
        }
        outputs = {}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        # Find the core function call
        req_idx = code.index("required_param,")
        opt_idx = code.index("optional_param=optional_param,")
        assert req_idx < opt_idx, "Required (positional) params should come before optional (keyword)"

    @pytest.mark.unit
    def test_hyphenated_names_sanitized(self):
        """Hyphens in param names should be converted to underscores."""
        cab_def = {
            "command": "pkg.core.run.run",
            "image": "ghcr.io/user/pkg:latest",
            "_name": "run",
        }
        inputs = {"input-file": {"dtype": "File", "required": True}}
        outputs = {"output-dir": {"dtype": "Directory", "policies": {"positional": True}}}

        lines = generate_function_body(cab_def, inputs, outputs)
        code = "\n".join(lines)

        assert "input_file," in code
        assert "output_dir," in code
        assert "input-file" not in code
        assert "output-dir" not in code

    @pytest.mark.unit
    def test_generated_code_compiles(self):
        """The generated body should be valid Python when wrapped in a function."""
        cab_def = {
            "command": "pfb_imaging.core.grid.grid",
            "image": "ghcr.io/user/pfb-imaging:latest",
            "_name": "grid",
        }
        inputs = {"ms": {"dtype": "MS", "required": True}}
        outputs = {"output-dir": {"dtype": "Directory", "policies": {}}}

        lines = generate_function_body(cab_def, inputs, outputs)
        # Wrap in a function to make it valid at module level
        func_code = "def grid(ms, output_dir=None, backend='auto', always_pull_images=False):\n"
        func_code += "\n".join(lines)

        compile(func_code, "<test>", "exec")
