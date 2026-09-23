"""Unit tests for the downstream-package harness helpers.

These run always and offline. The harness they support
(``test_downstream_roundtrip.py``) is opt-in and hits the network; everything
that can be decided without it lives here.
"""

from pathlib import Path

import pytest

from tests.downstream import (
    MANIFEST,
    Package,
    cache_dir,
    cli_modules,
    image_from_cabs,
    layout,
    load_manifest,
)


def _sdist(root: Path, package: str, *, cli: list[str], cabs: list[str], pyproject: bool = True) -> Path:
    """Build a synthetic unpacked sdist tree and return its root."""
    sdist_root = root / f"{package}-1.2.3"
    cli_dir = sdist_root / "src" / package / "cli"
    cabs_dir = sdist_root / "src" / package / "cabs"
    cli_dir.mkdir(parents=True)
    cabs_dir.mkdir(parents=True)
    for name in cli:
        (cli_dir / name).write_text("")
    for name in cabs:
        (cabs_dir / name).write_text("cabs: {}\n")
    if pyproject:
        (sdist_root / "pyproject.toml").write_text('[project]\nname = "x"\n')
    return sdist_root


# --- manifest ---------------------------------------------------------------


def test_load_manifest_reads_names_and_optional_pins(tmp_path):
    """A pin is optional; its absence means the latest release."""
    manifest = tmp_path / "downstream.toml"
    manifest.write_text(
        '[[package]]\nname = "pfb-imaging"\n\n[[package]]\nname = "pfb-model-spec"\nversion = "0.0.3"\n'
    )

    packages = load_manifest(manifest)

    assert packages == [
        Package(name="pfb-imaging", version=None),
        Package(name="pfb-model-spec", version="0.0.3"),
    ]


def test_load_manifest_rejects_an_entry_without_a_name(tmp_path):
    """A typo must fail loudly rather than silently testing nothing."""
    manifest = tmp_path / "downstream.toml"
    manifest.write_text('[[package]]\nversion = "0.0.3"\n')

    with pytest.raises(ValueError, match="name"):
        load_manifest(manifest)


def test_the_shipped_manifest_parses_and_is_not_empty():
    """The manifest in the repo must stay loadable."""
    packages = load_manifest(MANIFEST)

    assert packages
    assert all(p.name for p in packages)


# --- sdist layout -----------------------------------------------------------


def test_layout_finds_cli_cabs_and_pyproject(tmp_path):
    """Everything the round trip needs is in the sdist, in hip-cargo's own layout."""
    root = _sdist(tmp_path, "pfb_imaging", cli=["grid.py"], cabs=["grid.yml"])

    found = layout(root)

    assert found.cli_dir == root / "src" / "pfb_imaging" / "cli"
    assert found.cabs_dir == root / "src" / "pfb_imaging" / "cabs"
    assert found.pyproject == root / "pyproject.toml"
    assert found.import_name == "pfb_imaging"


def test_layout_returns_none_for_a_package_that_is_not_hip_cargo(tmp_path):
    """Not yet converted is a skip, not a failure."""
    root = tmp_path / "plain-1.2.3"
    (root / "src" / "plain").mkdir(parents=True)

    assert layout(root) is None


def test_layout_tolerates_a_missing_pyproject(tmp_path):
    """Ruff config is a nice-to-have; its absence must not crash discovery."""
    root = _sdist(tmp_path, "pkg", cli=["a.py"], cabs=["a.yml"], pyproject=False)

    found = layout(root)

    assert found is not None
    assert found.pyproject is None


# --- module discovery -------------------------------------------------------


def test_cli_modules_skips_dunder_and_private_modules(tmp_path):
    """pfb-imaging ships cli/_deprecation.py, which is not a command."""
    root = _sdist(
        tmp_path,
        "pkg",
        cli=["__init__.py", "_deprecation.py", "grid.py", "degrid.py"],
        cabs=["grid.yml", "degrid.yml"],
    )

    assert cli_modules(layout(root)) == ["degrid", "grid"]


def test_cli_modules_only_reports_modules_that_have_a_cab(tmp_path):
    """A command without a shipped cab has nothing to compare against."""
    root = _sdist(tmp_path, "pkg", cli=["grid.py", "serve.py"], cabs=["grid.yml"])

    assert cli_modules(layout(root)) == ["grid"]


# --- image ------------------------------------------------------------------


def test_image_is_read_from_the_shipped_cabs(tmp_path):
    """generate_cabs needs it explicitly; the dist is not installed."""
    root = _sdist(tmp_path, "pkg", cli=["grid.py"], cabs=[])
    (root / "src" / "pkg" / "cabs" / "grid.yml").write_text(
        "cabs:\n  grid:\n    image: ghcr.io/ratt-ru/pkg:0.1.0\n    inputs: {}\n"
    )

    assert image_from_cabs(layout(root).cabs_dir) == "ghcr.io/ratt-ru/pkg:0.1.0"


def test_image_is_none_when_no_cab_declares_one(tmp_path):
    """A package with no container image is legitimate."""
    root = _sdist(tmp_path, "pkg", cli=["grid.py"], cabs=["grid.yml"])

    assert image_from_cabs(layout(root).cabs_dir) is None


# --- cache ------------------------------------------------------------------


def test_cache_dir_honours_an_explicit_override(monkeypatch, tmp_path):
    """So a run can be pointed at a scratch directory."""
    monkeypatch.setenv("HIP_CARGO_DOWNSTREAM_CACHE", str(tmp_path / "somewhere"))

    assert cache_dir() == tmp_path / "somewhere"


def test_cache_dir_defaults_under_xdg_cache_home(monkeypatch, tmp_path):
    """Never inside the repository."""
    monkeypatch.delenv("HIP_CARGO_DOWNSTREAM_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    assert cache_dir() == tmp_path / "hip-cargo" / "downstream"
