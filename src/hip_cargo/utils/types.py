"""Custom types for comma-separated list parameters and URI paths."""

from typing import NewType

from upath import UPath

ListInt = NewType("ListInt", str)
ListFloat = NewType("ListFloat", str)
ListStr = NewType("ListStr", str)


def parse_list_int(value: str) -> list[int]:
    """Parse a comma-separated string into a list of integers."""
    return [int(x.strip()) for x in value.split(",")]


def parse_list_float(value: str) -> list[float]:
    """Parse a comma-separated string into a list of floats."""
    return [float(x.strip()) for x in value.split(",")]


def parse_list_str(value: str) -> list[str]:
    """Parse a comma-separated string into a list of strings."""
    return [x.strip() for x in value.split(",")]


def parse_upath(value: str) -> UPath:
    """Parse a CLI string into a universal Path (local or remote URI)."""
    return UPath(value)
