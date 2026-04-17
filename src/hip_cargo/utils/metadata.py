"""Hashable metadata container for stimela fields in Annotated type hints.

Python 3.10's ``typing.get_type_hints`` wraps any ``Annotated`` whose default is
``None`` in ``Optional[...]``. That triggers ``Union`` deduplication, which
hashes the annotation; ``Annotated.__hash__`` in turn hashes ``__metadata__``.
Plain ``dict`` metadata raises ``TypeError: unhashable type: 'dict'``.

``StimelaMeta`` replaces the legacy ``{"stimela": {...}}`` dict literal with an
immutable, Mapping-compatible container that is hashable even when constructed
from nested dicts or lists.
"""

from collections.abc import Mapping
from typing import Any, Iterator


class StimelaMeta(Mapping):
    """Hashable, dict-like container for stimela-specific Annotated metadata.

    Example:
        >>> Annotated[
        ...     Directory | None,
        ...     typer.Option(help="..."),
        ...     StimelaMeta(mkdir=False, path_policies={"write_parent": True}),
        ... ] = None
    """

    __slots__ = ("_items",)

    def __init__(self, **kwargs: Any) -> None:
        """Construct from keyword arguments. Nested dicts are wrapped recursively."""
        object.__setattr__(
            self,
            "_items",
            tuple((k, _freeze(v)) for k, v in kwargs.items()),
        )

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "StimelaMeta":
        """Construct from an existing mapping (e.g. the legacy dict form)."""
        return cls(**dict(mapping))

    def __getitem__(self, key: str) -> Any:
        for k, v in self._items:
            if k == key:
                return v
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (k for k, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: object) -> bool:
        return any(k == key for k, _ in self._items)

    def __hash__(self) -> int:
        return hash(self._items)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StimelaMeta):
            return self._items == other._items
        return NotImplemented

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self._items)
        return f"StimelaMeta({args})"

    def to_dict(self) -> dict[str, Any]:
        """Recursively thaw back to a plain dict (for YAML serialisation)."""
        return {k: _thaw(v) for k, v in self._items}


def _freeze(value: Any) -> Any:
    """Convert a value to a hashable, immutable form."""
    if isinstance(value, StimelaMeta):
        return value
    if isinstance(value, Mapping):
        return StimelaMeta(**dict(value))
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    """Recursively convert frozen values back to plain Python types."""
    if isinstance(value, StimelaMeta):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value
