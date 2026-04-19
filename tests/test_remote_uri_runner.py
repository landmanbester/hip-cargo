"""Tests for remote-URI-aware runner behaviour."""

from hip_cargo.utils.introspector import MS, URI, Directory, File
from hip_cargo.utils.runner import _is_path_type


def test_is_path_type_detects_upath_newtypes():
    assert _is_path_type(File) is True
    assert _is_path_type(Directory) is True
    assert _is_path_type(MS) is True
    assert _is_path_type(URI) is True


def test_is_path_type_detects_list_of_upath_newtype():
    assert _is_path_type(list[File]) is True
