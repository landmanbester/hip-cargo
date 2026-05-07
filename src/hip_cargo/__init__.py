"""hip-cargo: Tools for generating Stimela cab definitions."""

from upath import UPath

from hip_cargo.utils.config import get_container_image
from hip_cargo.utils.decorators import stimela_cab, stimela_output
from hip_cargo.utils.metadata import StimelaMeta
from hip_cargo.utils.types import (
    ListFloat,
    ListInt,
    ListStr,
    parse_list_float,
    parse_list_int,
    parse_list_str,
    parse_upath,
)

__version__ = "0.2.0"
__all__ = [
    "get_container_image",
    "stimela_cab",
    "stimela_output",
    "StimelaMeta",
    "ListInt",
    "ListFloat",
    "ListStr",
    "UPath",
    "parse_list_int",
    "parse_list_float",
    "parse_list_str",
    "parse_upath",
]
