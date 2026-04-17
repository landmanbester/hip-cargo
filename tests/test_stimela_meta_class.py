"""Tests for the StimelaMeta hashable metadata container."""

from typing import Annotated, get_args, get_origin, get_type_hints

import pytest

from hip_cargo import StimelaMeta


def test_hashable_simple():
    """StimelaMeta instances are hashable for primitive kwargs."""
    m = StimelaMeta(skip=True)
    assert hash(m) == hash(StimelaMeta(skip=True))


def test_hashable_with_nested_dict():
    """Nested dicts get frozen into nested StimelaMeta, keeping outer hashable."""
    m = StimelaMeta(mkdir=False, path_policies={"write_parent": True})
    assert hash(m) == hash(m)  # stable
    assert isinstance(m["path_policies"], StimelaMeta)


def test_hashable_with_list_value():
    """Lists are frozen into tuples so the container remains hashable."""
    m = StimelaMeta(choices=["a", "b", "c"])
    assert hash(m) is not None
    assert m["choices"] == ("a", "b", "c")


def test_mapping_protocol():
    """StimelaMeta supports get, __getitem__, __contains__, iter, len."""
    m = StimelaMeta(skip=True, mkdir=False)
    assert m["skip"] is True
    assert m.get("skip") is True
    assert m.get("missing", "fallback") == "fallback"
    assert "skip" in m
    assert "missing" not in m
    assert len(m) == 2
    assert set(iter(m)) == {"skip", "mkdir"}


def test_dict_unpacking():
    """StimelaMeta unpacks via ** into a plain dict."""
    m = StimelaMeta(skip=True, mkdir=False)
    unpacked = {**m}
    assert unpacked == {"skip": True, "mkdir": False}


def test_merge_with_dict():
    """Merging a plain dict with a StimelaMeta produces a plain dict."""
    base = {"access_parent": False}
    m = StimelaMeta(write_parent=True)
    merged = {**base, **m}
    assert merged == {"access_parent": False, "write_parent": True}


def test_nested_access_returns_stimela_meta():
    """Nested dict values are accessible as further StimelaMeta instances."""
    m = StimelaMeta(path_policies={"write_parent": True, "access_parent": False})
    nested = m["path_policies"]
    assert isinstance(nested, StimelaMeta)
    assert nested["write_parent"] is True
    assert nested.get("access_parent") is False


def test_equality():
    """Equality compares the underlying frozen items."""
    a = StimelaMeta(skip=True)
    b = StimelaMeta(skip=True)
    c = StimelaMeta(skip=False)
    assert a == b
    assert a != c
    assert a != {"skip": True}  # plain dict is not equal


def test_to_dict_roundtrip():
    """to_dict recursively thaws back to plain dicts/lists."""
    original = {"mkdir": False, "path_policies": {"write_parent": True}, "choices": ["x", "y"]}
    m = StimelaMeta.from_mapping(original)
    assert m.to_dict() == original


def test_from_mapping():
    """from_mapping constructs from any Mapping."""
    m = StimelaMeta.from_mapping({"skip": True})
    assert m == StimelaMeta(skip=True)


def test_empty():
    """Empty StimelaMeta is valid."""
    m = StimelaMeta()
    assert len(m) == 0
    assert list(iter(m)) == []
    assert m.to_dict() == {}
    assert hash(m) == hash(StimelaMeta())


def test_repr():
    """Repr shows kwargs form for readability."""
    m = StimelaMeta(skip=True, mkdir=False)
    r = repr(m)
    assert r.startswith("StimelaMeta(")
    assert "skip=True" in r
    assert "mkdir=False" in r


def test_regression_python_310_optional_wrap():
    """Annotated with StimelaMeta metadata must hash cleanly.

    Regression test for Python 3.10's ``get_type_hints`` wrapping ``Annotated``
    whose default is ``None`` in ``Optional[...]``. Any metadata item that is
    unhashable (plain dict) blows up during Union deduplication. StimelaMeta
    is hashable, so this must succeed on all supported Pythons.
    """

    def f(x: Annotated[str, "info", StimelaMeta(skip=True)] = None) -> None:
        pass

    hints = get_type_hints(f, include_extras=True)
    annotation = hints["x"]
    # Must be Annotated and hashable
    assert get_origin(annotation) is Annotated
    assert hash(annotation) is not None
    # StimelaMeta survives in __metadata__
    metas = get_args(annotation)[1:]
    assert any(isinstance(m, StimelaMeta) for m in metas)


def test_keyerror_on_missing():
    """__getitem__ raises KeyError for missing keys."""
    m = StimelaMeta(skip=True)
    with pytest.raises(KeyError):
        _ = m["missing"]
