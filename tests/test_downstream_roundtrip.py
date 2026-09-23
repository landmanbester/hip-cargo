"""Opt-in: do released downstream packages still round-trip under this hip-cargo?

Run before cutting a release:

    HIP_CARGO_DOWNSTREAM=1 uv run pytest tests/test_downstream_roundtrip.py

Each entry in ``tests/downstream.toml`` is tested from its sdist — no install,
no clone — because the sdist carries everything the round trip needs:
``src/<pkg>/cli/``, ``src/<pkg>/cabs/`` and the ``pyproject.toml`` whose ruff
config decides the formatting of regenerated source. Downloads are cached, so
only the first run needs the network.

Two properties, asserted separately so a failure says which direction broke:

* the cab we generate from a shipped CLI module still *means* the same as the
  shipped cab (compared as parsed YAML — text-level churn from an emitter
  improvement is fine, a changed value is not);
* the CLI module we generate from a shipped cab is byte-identical to the
  shipped one, which is what the downstream's own round-trip test asserts.
"""

import os

import pytest
import yaml

from hip_cargo.core.generate_cabs import generate_cabs
from hip_cargo.core.generate_function import generate_function
from tests.downstream import cli_modules, image_from_cabs, load_manifest, prepare

if not os.environ.get("HIP_CARGO_DOWNSTREAM"):
    pytest.skip(
        "downstream harness is opt-in: set HIP_CARGO_DOWNSTREAM=1 (needs network on first run)",
        allow_module_level=True,
    )


def _discover():
    """Resolve every manifest entry into one case per CLI module."""
    cases = []
    for package in load_manifest():
        version, found = prepare(package)
        if found is None:
            cases.append(
                pytest.param(
                    None,
                    None,
                    id=f"{package.name}-{version}",
                    marks=pytest.mark.skip(reason=f"{package.name} {version} is not a hip-cargo package"),
                )
            )
            continue
        for module in cli_modules(found):
            cases.append(pytest.param(found, module, id=f"{package.name}-{version}:{module}"))
    return cases


CASES = _discover()


@pytest.mark.integration
@pytest.mark.parametrize("found,module", CASES)
def test_the_shipped_cab_is_what_we_would_generate(found, module, tmp_path):
    """A released package's cab must still be the one this hip-cargo emits."""
    generate_cabs(
        [found.cli_dir / f"{module}.py"],
        output_dir=tmp_path,
        image=image_from_cabs(found.cabs_dir),
    )

    with open(found.cabs_dir / f"{module}.yml") as f:
        shipped = yaml.safe_load(f)
    with open(tmp_path / f"{module}.yml") as f:
        generated = yaml.safe_load(f)

    assert generated == shipped


@pytest.mark.integration
@pytest.mark.parametrize("found,module", CASES)
def test_the_shipped_cli_regenerates_from_its_cab(found, module, tmp_path):
    """And the reverse direction must still reproduce the source exactly."""
    regenerated = tmp_path / f"{module}.py"
    generate_function(
        found.cabs_dir / f"{module}.yml",
        output_file=regenerated,
        config_file=found.pyproject,
    )

    original_lines = (found.cli_dir / f"{module}.py").read_text().splitlines()
    generated_lines = regenerated.read_text().splitlines()

    assert len(generated_lines) == len(original_lines), (
        f"line count: shipped {len(original_lines)}, regenerated {len(generated_lines)}"
    )
    for number, (shipped_line, generated_line) in enumerate(zip(original_lines, generated_lines), 1):
        assert shipped_line == generated_line, (
            f"line {number} differs:\n  shipped:     {shipped_line}\n  regenerated: {generated_line}"
        )
