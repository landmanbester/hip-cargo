"""Custom types for comma-separated list parameters and URI paths."""

from typing import NewType

from upath import UPath

ListInt = NewType("ListInt", str)
ListFloat = NewType("ListFloat", str)
ListStr = NewType("ListStr", str)


def parse_list_int(value: str | list[int]) -> list[int]:
    """Parse a comma-separated string into a list of integers.

    List values (e.g. an already-parsed default) pass through untouched,
    since typer applies the parser to defaults as well as CLI input.
    """
    if isinstance(value, list):
        return value
    return [int(x.strip()) for x in value.split(",")]


def parse_list_float(value: str | list[float]) -> list[float]:
    """Parse a comma-separated string into a list of floats.

    List values (e.g. an already-parsed default) pass through untouched.
    """
    if isinstance(value, list):
        return value
    return [float(x.strip()) for x in value.split(",")]


def parse_list_str(value: str | list[str]) -> list[str]:
    """Parse a comma-separated string into a list of strings.

    List values (e.g. an already-parsed default) pass through untouched.
    """
    if isinstance(value, list):
        return value
    return [x.strip() for x in value.split(",")]


def parse_upath(value: str) -> UPath:
    """Parse a CLI string into a universal Path (local or remote URI)."""
    return UPath(value)


# Map stimela List dtypes to their comma-separated-string parsers. Shared by
# cab generation (introspector) and function generation (cab_to_function) so
# whitespace and element-casting semantics cannot drift between the two paths.
LIST_DTYPE_PARSERS = {
    "List[int]": parse_list_int,
    "List[float]": parse_list_float,
    "List[str]": parse_list_str,
}
