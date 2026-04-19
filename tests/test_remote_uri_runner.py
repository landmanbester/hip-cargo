"""Tests for remote-URI-aware runner behaviour.

Subsequent tasks (6, 7, 9, 10, 11) append additional test functions here.
"""

from typing import Annotated

import typer
from upath import UPath

from hip_cargo.utils.introspector import MS, URI, Directory, File
from hip_cargo.utils.runner import (
    _collect_remote_protocols,
    _is_path_type,
    _is_remote_upath,
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
