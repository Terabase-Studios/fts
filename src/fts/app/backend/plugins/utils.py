import functools
import types
from typing import Callable


def copy_func(f: Callable) -> Callable:
    g = types.FunctionType(
        f.__code__,
        f.__globals__,
        name=f.__name__,
        argdefs=f.__defaults__,
        closure=f.__closure__
    )
    g = functools.update_wrapper(g, f)
    g.__kwdefaults__ = getattr(f, "__kwdefaults__", None)
    return g