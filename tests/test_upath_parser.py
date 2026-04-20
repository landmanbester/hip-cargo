"""Tests for parse_upath and UPath re-export."""

from upath import UPath

from hip_cargo import UPath as ReexportedUPath
from hip_cargo.utils.types import parse_upath


def test_parse_upath_local_path():
    result = parse_upath("/tmp/foo")
    assert isinstance(result, UPath)
    assert result.protocol in ("", "file", "local")
    assert str(result) == "/tmp/foo"


def test_parse_upath_relative_path():
    result = parse_upath("data/x.fits")
    assert isinstance(result, UPath)
    assert result.protocol in ("", "file", "local")


def test_parse_upath_s3_uri():
    result = parse_upath("s3://my-bucket/key.fits")
    assert isinstance(result, UPath)
    assert result.protocol == "s3"


def test_parse_upath_gcs_uri():
    result = parse_upath("gs://my-bucket/key.fits")
    assert isinstance(result, UPath)
    assert result.protocol in ("gs", "gcs")


def test_parse_upath_memory_uri():
    result = parse_upath("memory:///scratch/x.bin")
    assert isinstance(result, UPath)
    assert result.protocol == "memory"


def test_upath_reexport_identity():
    assert ReexportedUPath is UPath
