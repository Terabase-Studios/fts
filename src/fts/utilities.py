import asyncio
import re
import time

from fts.config import USE_UVLOOP, USE_WINLOOP, CONFIG_FILE


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    power = 1024
    n = 0
    s = float(size)

    while s >= power and n < len(units) - 1:
        s /= power
        n += 1

    return f"{s:.2f} {units[n]}"


def parse_byte_string(size_str) -> int:
    """
    Convert a human-readable size string into bytes.
    Examples:
        "1GB" -> 1073741824
        "512MB" -> 536870912
        "10KB" -> 10240
        "123" -> 123
    """
    try:
        size = int(size_str)
        return size
    except ValueError:
        pass

    size_str = size_str.strip().upper()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)?", size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")

    number, unit = match.groups()
    number = float(number)
    unit_multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
        None: 1,  # if no unit, assume bytes
    }
    return int(number * unit_multipliers[unit])


def install_fast_event_loop(debug_prints=False):
    """
    Configure asyncio to use uvloop or winloop globally.

    Must be called once at program startup, before any loops are created.

    Returns:
        success: bool
    """
    if USE_UVLOOP:
        try:
            import uvloop
            if debug_prints:
                print("[FTS-TOOL][INFO]: Uvloop Acceleration Active")
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except ImportError:
            print(f"\033[33m[FTS-TOOL][WARNING]: UvLoop not found! Unable to activate uvloop acceleration. \nPlease install uvloop or deactivate `use_uv_or_win_loop_acceleration` in {CONFIG_FILE}\033[0m")
            return False # fallback to default asyncio
    elif USE_WINLOOP:
        try:
            import winloop
            if debug_prints:
                print("[FTS-TOOL][INFO]: Winloop Acceleration Active")
            asyncio.set_event_loop_policy(winloop.EventLoopPolicy())
        except ImportError:
            print(f"\033[33m[FTS-TOOL][WARNING]: WinLoop not found! Unable to activate winloop acceleration. \nPlease install winloop or deactivate `use_uv_or_win_loop_acceleration` in {CONFIG_FILE}\033[0m")
            return False # fallback to default asyncio


def run_async(main, *, debug=None):
    """
    Drop-in replacement for asyncio.run / uvloop.run.

    Args:
        main: Coroutine to execute
        debug: Optional debug flag

    Returns:
        Result of the coroutine
    """

    if USE_UVLOOP:
        try:
            import uvloop
        except ImportError:
            return asyncio.run(main, debug=debug)
        return uvloop.run(main, debug=debug)
    elif USE_WINLOOP:
        try:
            import winloop
        except ImportError:
            return asyncio.run(main, debug=debug)
        return winloop.run(main, debug=debug)
    else:
        return asyncio.run(main, debug=debug)