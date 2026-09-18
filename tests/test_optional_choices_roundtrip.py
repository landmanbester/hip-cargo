"""Round-trip tests for optional parameters with ``choices`` (issue #90).

An optional parameter with choices must be ``Literal[...] | None`` in the CLI,
and that annotation must survive ``cli → cab → cli`` unchanged.
"""

import tempfile
from pathlib import Path

import yaml

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function
from hip_cargo.utils.cab_to_function import generate_parameter_signature

FIXTURE_CLI = Path("tests/fixtures/src/fixture_pkg/cli/choices_demo.py")


def test_forward_optional_literal_emits_choices():
    """generate-cabs accepts ``Literal[...] | None`` and emits plain choices."""
    with tempfile.TemporaryDirectory() as tmp:
        cab_dir = Path(tmp) / "cabs"
        cab_dir.mkdir()
        generate_cabs([FIXTURE_CLI], output_dir=cab_dir)

        with open(cab_dir / "choices_demo.yml") as f:
            inputs = yaml.safe_load(f)["cabs"]["choices_demo"]["inputs"]

        assert inputs["beam-model"]["choices"] == ["meerkat-beams", "katbeam"]
        assert "default" not in inputs["beam-model"]
        assert "required" not in inputs["beam-model"]
        assert inputs["mode"]["choices"] == ["fast", "slow"]
        assert inputs["mode"]["default"] == "fast"


def test_reverse_optional_dtype_with_choices_is_optional():
    """``dtype: Optional[str]`` + choices generates ``Literal[...] | None``."""
    sig = generate_parameter_signature(
        "beam-model",
        {"info": "Which beam model to use.", "dtype": "Optional[str]", "choices": ["meerkat-beams"]},
    )
    assert "Literal['meerkat-beams'] | None," in sig
    assert sig.endswith("] = None,")


def test_reverse_choices_without_default_is_optional():
    """Choices with no default and not required default to None, so the type is optional."""
    sig = generate_parameter_signature("beam-model", {"info": "Beam.", "choices": ["a", "b"]})
    assert "Literal['a', 'b'] | None," in sig


def test_reverse_choices_with_default_stays_non_optional():
    sig = generate_parameter_signature("mode", {"info": "Mode.", "choices": ["fast", "slow"], "default": "fast"})
    assert "Literal['fast', 'slow']," in sig
    assert "| None" not in sig


def test_reverse_required_choices_stays_non_optional():
    sig = generate_parameter_signature("mode", {"info": "Mode.", "choices": ["fast", "slow"], "required": True})
    assert "| None" not in sig


def test_choices_demo_line_for_line_roundtrip():
    """cli → cab → cli is line-for-line identical for the choices fixture."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cab_dir = tmp / "cabs"
        cab_dir.mkdir()
        generate_cabs([FIXTURE_CLI], output_dir=cab_dir)

        regen = tmp / "choices_demo_regen.py"
        generate_function(
            cab_dir / "choices_demo.yml",
            output_file=regen,
            config_file=Path("pyproject.toml"),
        )

        original_lines = FIXTURE_CLI.read_text().splitlines()
        regen_lines = regen.read_text().splitlines()

        assert len(original_lines) == len(regen_lines), (
            f"line count differs: original={len(original_lines)} regen={len(regen_lines)}"
        )
        for i, (orig, gen) in enumerate(zip(original_lines, regen_lines), 1):
            assert orig == gen, f"line {i} differs:\n  original: {orig!r}\n  regen:    {gen!r}"
