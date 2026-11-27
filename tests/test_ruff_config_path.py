"""A relative ruff config path must work from any working directory.

Both generators run ruff from the config file's directory, so the path they pass
to ``--config`` has to be absolute; a relative one used to miss and leave the code
unformatted with only a warning. A remote config is rejected outright.
"""

import warnings
from pathlib import Path

import pytest
from upath import UPath

from hip_cargo.core.generate_function import generate_function
from hip_cargo.core.generate_schemas import _ruff_format, generate_schemas

REPO = Path(__file__).parents[1]
CAB = REPO / "src" / "hip_cargo" / "cabs" / "generate_cabs.yml"
FIXTURE_CLI = REPO / "tests" / "fixtures" / "src" / "fixture_pkg" / "cli" / "tunable_demo.py"


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


def test_a_symlinked_config_keeps_its_relative_extend(tmp_path: Path) -> None:
    """The config is passed as given, not resolved, so `extend` is read next to the link."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "ruff.toml").write_text('extend = "base.toml"\n')
    project = tmp_path / "project"
    project.mkdir()
    (project / "base.toml").write_text('[format]\nquote-style = "double"\n')
    (project / "ruff.toml").symlink_to(real / "ruff.toml")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _ruff_format("x = 'a'\n", config_file=project / "ruff.toml") == 'x = "a"\n'


def test_generate_function_warns_when_the_config_directory_is_missing(tmp_path: Path) -> None:
    """A config in a missing directory is an invalid ruff cwd; fall back with a warning, don't crash."""
    output = tmp_path / "out.py"
    with pytest.warns(UserWarning, match="ruff failed"):
        generate_function(CAB, output_file=output, config_file=tmp_path / "nope" / "pyproject.toml")
    assert output.exists()


@pytest.mark.parametrize("uri", ["memory://configs/pyproject.toml", "s3://bucket/pyproject.toml"])
def test_a_remote_config_is_rejected_before_any_output(uri: str, tmp_path: Path) -> None:
    """ruff reads only local files, so a remote config is an error, not an unformatted fallback."""
    output = tmp_path / "out.py"
    with pytest.raises(ValueError, match="must be a local file"):
        generate_function(CAB, output_file=output, config_file=UPath(uri))
    assert not output.exists()
    with pytest.raises(ValueError, match="must be a local file"):
        generate_schemas([FIXTURE_CLI], output_dir=tmp_path / "schemas", config_file=UPath(uri))
    assert not (tmp_path / "schemas").exists()


def test_a_file_uri_config_is_read_as_a_local_path(relative_config: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        uri = UPath(relative_config.absolute().as_uri())
        assert _ruff_format("x = 'a'\n", config_file=uri) == 'x = "a"\n'
