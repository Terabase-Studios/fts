import re

def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    power = 1024
    n = 0
    s = float(size)

    while s >= power and n < len(units) - 1:
        s /= power
        n += 1

    return f"{s:.2f} {units[n]}"

def parse_byte_string(size_str: str | int) -> int:
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
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
        None: 1,  # if no unit, assume bytes
    }
    return int(number * unit_multipliers[unit])
