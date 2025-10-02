"""Decorators for marking functions as Stimela cabs."""

from typing import Any, Callable, Optional


def stimela_cab(
    name: str,
    info: str,
    policies: Optional[dict[str, Any]] = None,
    **kwargs: Any,
) -> Callable:
    """
    Decorator to mark a function as a Stimela cab.

    Args:
        name: Name of the cab
        info: Description of what the cab does
        policies: Optional cab-level policies
        **kwargs: Additional cab metadata
    """

    def decorator(func: Callable) -> Callable:
        # Store metadata on the function object
        func.__stimela_cab_config__ = {
            "name": name,
            "info": info,
            "policies": policies or {},
            **kwargs,
        }
        return func

    return decorator


def stimela_output(
    name: str,
    dtype: str,
    info: str = "",
    required: bool = False,
) -> Callable:
    """
    Decorator to define an output of a Stimela cab.

    Can be stacked multiple times for multiple outputs.

    Args:
        name: Name of the output
        dtype: Data type (File, Directory, MS, int, str, etc.)
        info: Description (can include f-string patterns like {input_param})
        required: Whether this output is required
    """

    def decorator(func: Callable) -> Callable:
        # Initialize outputs list if it doesn't exist
        if not hasattr(func, "__stimela_outputs__"):
            func.__stimela_outputs__ = []

        # Append this output definition
        func.__stimela_outputs__.append(
            {
                "name": name,
                "dtype": dtype,
                "info": info,
                "required": required,
            }
        )

        return func

    return decorator
