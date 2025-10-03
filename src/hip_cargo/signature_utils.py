# signature_utils.py (if you want to make this reusable)
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def inherit_signature(base_func: Callable[P, R]) -> Callable[[Callable], Callable[P, R]]:
    """
    Decorator that makes a function inherit the signature of base_func.

    Usage:
        @inherit_signature(original_function)
        def my_wrapper(*args, **kwargs):
            # Your custom logic
            return original_function(*args, **kwargs)
    """

    def decorator(wrapper_func: Callable) -> Callable[P, R]:
        @wraps(base_func)
        def inner(*args: P.args, **kwargs: P.kwargs) -> R:
            return wrapper_func(*args, **kwargs)

        return inner

    return decorator
