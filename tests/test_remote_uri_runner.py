"""Tests for remote-URI-aware runner behaviour.

Subsequent tasks (6, 7, 9, 10, 11) append additional test functions here.
"""

from typing import Annotated

import fsspec
import pytest
import typer
from upath import UPath

from hip_cargo.utils.introspector import MS, URI, Directory, File
from hip_cargo.utils.metadata import StimelaMeta
from hip_cargo.utils.runner import (
    _collect_remote_protocols,
    _is_path_type,
    _is_remote_upath,
    _resolve_mounts,
    preflight_remote_must_exist,
)


def test_is_path_type_detects_upath_newtypes():
    assert _is_path_type(File) is True
    assert _is_path_type(Directory) is True
    assert _is_path_type(MS) is True
    assert _is_path_type(URI) is True


def test_is_path_type_detects_list_of_upath_newtype():
    assert _is_path_type(list[File]) is True


def test_is_remote_upath_local():
    assert _is_remote_upath(UPath("/tmp/x")) is False


def test_is_remote_upath_memory():
    assert _is_remote_upath(UPath("memory:///scratch/x")) is True


def test_is_remote_upath_s3():
    assert _is_remote_upath(UPath("s3://bkt/k")) is True


def test_collect_remote_protocols_mixed():
    def fn(
        a: Annotated[File, typer.Option()] = UPath("/tmp/a"),  # noqa: B008
        b: Annotated[File, typer.Option()] = UPath("s3://bkt/b"),  # noqa: B008
        c: Annotated[File, typer.Option()] = UPath("memory:///c"),  # noqa: B008
    ) -> None:
        pass

    params = {
        "a": UPath("/tmp/a"),
        "b": UPath("s3://bkt/b"),
        "c": UPath("memory:///c"),
    }
    protocols = _collect_remote_protocols(fn, params)
    assert protocols == {"s3", "memory"}


def test_collect_remote_protocols_all_local():
    def fn(a: Annotated[File, typer.Option()] = UPath("/tmp/a")) -> None:  # noqa: B008
        pass

    assert _collect_remote_protocols(fn, {"a": UPath("/tmp/a")}) == set()


def test_collect_remote_protocols_none_value():
    def fn(a: Annotated[File | None, typer.Option()] = None) -> None:
        pass

    assert _collect_remote_protocols(fn, {"a": None}) == set()


def test_collect_remote_protocols_list_of_paths():
    def fn(xs: Annotated[list[File], typer.Option()] = ()) -> None:  # noqa: B008
        pass

    params = {
        "xs": [
            UPath("/tmp/a"),
            UPath("s3://bkt/x"),
            UPath("memory:///c"),
        ]
    }
    assert _collect_remote_protocols(fn, params) == {"s3", "memory"}


def test_resolve_mounts_skips_remote_upaths(tmp_path):
    local = tmp_path / "local.fits"
    local.write_bytes(b"data")

    def fn(
        a: Annotated[File, typer.Option()] = UPath(str(local)),  # noqa: B008
        b: Annotated[File, typer.Option()] = UPath("s3://bkt/k"),  # noqa: B008
    ) -> None:
        pass

    params = {"a": UPath(str(local)), "b": UPath("s3://bkt/k")}
    mounts = _resolve_mounts(fn, params)

    # Remote param contributes nothing.
    assert not any("s3" in p or "bkt" in p for p in mounts)
    # Local param still produces a mount.
    assert any(str(tmp_path) in p for p in mounts)


def test_preflight_passes_for_existing_remote_upath():
    fs = fsspec.filesystem("memory")
    with fs.open("/present.bin", "wb") as f:
        f.write(b"x")

    def fn(
        x: Annotated[File, typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            "memory:///present.bin"
        ),
    ) -> None:
        pass

    preflight_remote_must_exist(fn, {"x": UPath("memory:///present.bin")})


def test_preflight_fails_for_missing_remote_upath():
    def fn(
        x: Annotated[File, typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            "memory:///absent.bin"
        ),
    ) -> None:
        pass

    with pytest.raises(typer.Exit):
        preflight_remote_must_exist(fn, {"x": UPath("memory:///absent.bin")})


def test_preflight_ignores_local_paths(tmp_path):
    missing = tmp_path / "does-not-exist.bin"

    def fn(
        x: Annotated[File, typer.Option(), StimelaMeta(must_exist=True)] = UPath(  # noqa: B008
            str(missing)
        ),
    ) -> None:
        pass

    # Local paths are not pre-flighted here — mount logic owns that contract.
    preflight_remote_must_exist(fn, {"x": UPath(str(missing))})


def test_preflight_ignores_params_without_must_exist():
    def fn(
        x: Annotated[File, typer.Option()] = UPath("memory:///nope.bin"),  # noqa: B008
    ) -> None:
        pass

    # No StimelaMeta(must_exist=True) → skip.
    preflight_remote_must_exist(fn, {"x": UPath("memory:///nope.bin")})
