"""Helpers for the opt-in downstream-package round-trip harness.

The property under test is that a *released* hip-cargo package's committed
``cli/`` and ``cabs/`` still agree under this hip-cargo. Everything needed for
that is in the package's sdist — ``src/<pkg>/cli/``, ``src/<pkg>/cabs/`` and
``pyproject.toml`` — so the harness downloads and unpacks one rather than
installing the package or cloning its repository. Neither generator imports the
package; both are pure CST/YAML over files.

See ``tests/downstream.toml`` for the manifest and
``tests/test_downstream_roundtrip.py`` for the harness itself.
"""

from __future__ import annotations

import json
import os
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib

MANIFEST = Path(__file__).parent / "downstream.toml"
PYPI_JSON = "https://pypi.org/pypi/{name}/json"


@dataclass(frozen=True)
class Package:
    """A manifest entry: a distribution, optionally pinned."""

    name: str
    version: str | None = None


@dataclass(frozen=True)
class SdistLayout:
    """Where the round trip's inputs live inside an unpacked sdist."""

    root: Path
    import_name: str
    cli_dir: Path
    cabs_dir: Path
    pyproject: Path | None


def load_manifest(path: Path = MANIFEST) -> list[Package]:
    """Read the downstream manifest.

    Args:
        path: TOML manifest with a ``[[package]]`` array.

    Returns:
        The packages to test, in manifest order.

    Raises:
        ValueError: If an entry has no ``name``.
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)

    packages = []
    for entry in data.get("package", []):
        name = entry.get("name")
        if not name:
            raise ValueError(f"{path}: every [[package]] entry needs a name, got {entry!r}")
        packages.append(Package(name=name, version=entry.get("version")))
    return packages


def cache_dir() -> Path:
    """Where downloaded sdists are kept, so repeat runs are offline.

    Never inside the repository: ``HIP_CARGO_DOWNSTREAM_CACHE`` if set, else
    under ``XDG_CACHE_HOME`` (default ``~/.cache``).
    """
    override = os.environ.get("HIP_CARGO_DOWNSTREAM_CACHE")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "hip-cargo" / "downstream"


def layout(root: Path) -> SdistLayout | None:
    """Locate the CLI and cab directories inside an unpacked sdist.

    Args:
        root: Directory the sdist unpacked to (``<name>-<version>/``).

    Returns:
        The layout, or ``None`` if this is not a hip-cargo package — a package
        that has not been converted yet is a skip, not a failure.
    """
    for pkg_dir in sorted((root / "src").glob("*")):
        cli_dir = pkg_dir / "cli"
        cabs_dir = pkg_dir / "cabs"
        if cli_dir.is_dir() and cabs_dir.is_dir():
            pyproject = root / "pyproject.toml"
            return SdistLayout(
                root=root,
                import_name=pkg_dir.name,
                cli_dir=cli_dir,
                cabs_dir=cabs_dir,
                pyproject=pyproject if pyproject.is_file() else None,
            )
    return None


def cli_modules(found: SdistLayout) -> list[str]:
    """Command modules to round-trip.

    Skips ``__init__`` and underscore-prefixed helpers (pfb-imaging ships
    ``cli/_deprecation.py``), and anything without a shipped cab — a command
    deliberately left uncabbed, like surfvis's ``serve``, has nothing to
    compare against.
    """
    return sorted(
        path.stem
        for path in found.cli_dir.glob("*.py")
        if not path.stem.startswith("_") and (found.cabs_dir / f"{path.stem}.yml").is_file()
    )


def image_from_cabs(cabs_dir: Path) -> str | None:
    """Container image declared by the shipped cabs, if any.

    ``generate_cabs`` resolves this from installed distribution metadata, which
    is unavailable here — nothing is installed — so the harness passes it
    explicitly. Reading it back out of the shipped cabs is deliberate: it
    neutralises the field. Whether a released package's ``image:`` agrees with
    its own ``_container_image.py`` is that package's business, checked by its
    own round-trip suite; a disagreement must not fail a harness that is asking
    whether *hip-cargo* still round-trips it.
    """
    for cab_file in sorted(cabs_dir.glob("*.yml")):
        with open(cab_file) as f:
            data = yaml.safe_load(f) or {}
        for cab_def in (data.get("cabs") or {}).values():
            image = cab_def.get("image")
            if image:
                return image
    return None


def resolve_version(package: Package) -> str:
    """The pinned version, or the latest release on PyPI."""
    if package.version:
        return package.version
    with urllib.request.urlopen(PYPI_JSON.format(name=package.name)) as response:
        return json.load(response)["info"]["version"]


def fetch_sdist(name: str, version: str) -> Path:
    """Download the sdist for a release, caching it.

    Returns:
        Path to the downloaded archive.

    Raises:
        LookupError: If the release publishes no sdist.
    """
    destination = cache_dir() / name
    destination.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(PYPI_JSON.format(name=name)) as response:
        release = json.load(response)["releases"].get(version, [])

    for artifact in release:
        if artifact["packagetype"] != "sdist":
            continue
        archive = destination / artifact["filename"]
        if not archive.is_file():
            with urllib.request.urlopen(artifact["url"]) as source:
                archive.write_bytes(source.read())
        return archive

    raise LookupError(f"{name} {version} publishes no sdist")


def unpack(archive: Path) -> Path:
    """Unpack an sdist beside itself, once, and return its root directory."""
    root = archive.parent / archive.name.removesuffix(".tar.gz")
    if not root.is_dir():
        with tarfile.open(archive) as tar:
            tar.extractall(archive.parent, filter="data")
    return root


def prepare(package: Package) -> tuple[str, SdistLayout | None]:
    """Resolve, download and unpack a manifest entry.

    Returns:
        ``(version, layout)``; the layout is ``None`` for a package that is not
        a hip-cargo package.
    """
    version = resolve_version(package)
    return version, layout(unpack(fetch_sdist(package.name, version)))
