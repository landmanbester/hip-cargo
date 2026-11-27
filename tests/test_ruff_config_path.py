"""A relative ruff config path must work from any working directory.

Both generators run ruff from the config file's directory, so the path they pass
to ``--config`` has to be absolute; a relative one used to miss and silently
skip formatting.
"""

import warnings
from pathlib import Path

import pytest

from hip_cargo.core.generate_function import generate_function
from hip_cargo.core.generate_schemas import _ruff_format

CAB = Path(__file__).parents[1] / "src" / "hip_cargo" / "cabs" / "generate_cabs.yml"


@pytest.fixture
def relative_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ruff config in a subdirectory, named relative to the working directory."""
    project = tmp_path / "project"
    project.mkdir()
    # The scaffolded project's ruff settings; an explicit select keeps ruff's
    # default rule set (which flags generated code) out of the test.
    (project / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 120\n\n"
        '[tool.ruff.lint]\nselect = ["E", "F", "I", "N", "W"]\n\n'
        '[tool.ruff.format]\nquote-style = "double"\n'
    )
    monkeypatch.chdir(tmp_path)
    return Path("project") / "pyproject.toml"


def test_generate_function_formats_with_a_relative_config(relative_config: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.py"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        generate_function(CAB, output_file=output, config_file=relative_config)
    # Unformatted output keeps the generator's single-quoted literals.
    assert "== 'native'" not in output.read_text()


def test_generate_schemas_formats_with_a_relative_config(relative_config: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _ruff_format("x = 'a'\n", config_file=relative_config) == 'x = "a"\n'
