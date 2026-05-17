"""Round-trip tests for the ``metadata.tunable`` flag.

Exercises the full ``cli → cab → cli`` round-trip on a fixture CLI module
that mixes ``StimelaMeta(metadata={"tunable": True})`` with
``rich_help_panel`` (the most interesting case for the metadata-merge logic).
"""

import tempfile
from pathlib import Path

import yaml

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function

FIXTURE_CLI = Path("tests/fixtures/src/fixture_pkg/cli/tunable_demo.py")


def test_forward_cab_carries_metadata_tunable():
    """generate-cabs emits both rich_help_panel and tunable under metadata."""
    with tempfile.TemporaryDirectory() as tmp:
        cab_dir = Path(tmp) / "cabs"
        cab_dir.mkdir()
        generate_cabs([FIXTURE_CLI], output_dir=cab_dir)

        with open(cab_dir / "tunable_demo.yml") as f:
            cab = yaml.safe_load(f)

        inputs = cab["cabs"]["tunable_demo"]["inputs"]

        # Both flags coexist under metadata (tests the forward merge fix).
        assert inputs["n-iter"]["metadata"] == {"rich_help_panel": "Tuning", "tunable": True}
        assert inputs["threshold"]["metadata"] == {"rich_help_panel": "Tuning", "tunable": True}

        # Non-tunable param keeps only rich_help_panel.
        assert inputs["label"]["metadata"] == {"rich_help_panel": "Inputs"}


def test_reverse_regenerates_stimela_meta_tunable():
    """generate-function reconstructs StimelaMeta(metadata={"tunable": True})."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cab_dir = tmp / "cabs"
        cab_dir.mkdir()
        generate_cabs([FIXTURE_CLI], output_dir=cab_dir)

        regen = tmp / "regen.py"
        generate_function(
            cab_dir / "tunable_demo.yml",
            output_file=regen,
            config_file=Path("pyproject.toml"),
        )

        code = regen.read_text()

        # rich_help_panel routed back into typer.Option, tunable into StimelaMeta.
        assert 'rich_help_panel="Tuning"' in code
        assert 'rich_help_panel="Inputs"' in code
        assert '"tunable": True' in code
        # The non-tunable param must NOT have a StimelaMeta block.
        assert code.count("StimelaMeta(") == 2


def test_tunable_demo_line_for_line_roundtrip():
    """cli → cab → cli is line-for-line identical for the tunable fixture."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cab_dir = tmp / "cabs"
        cab_dir.mkdir()
        generate_cabs([FIXTURE_CLI], output_dir=cab_dir)

        regen = tmp / "tunable_demo_regen.py"
        generate_function(
            cab_dir / "tunable_demo.yml",
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
