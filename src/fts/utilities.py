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


def fix_json_id_conflicts(start_id: int = 100):
    from pathlib import Path
    from fts.config import IN_PROGRESS_DIR
    import json

    base = Path(IN_PROGRESS_DIR)
    if not base.exists():
        return

    used_ids = set()
    next_id = start_id

    def get_next_free():
        nonlocal next_id
        while next_id in used_ids:
            next_id += 1
        val = next_id
        used_ids.add(val)
        next_id += 1
        return val

    for file in base.glob("*.json"):
        try:
            with open(file, "r") as f:
                data = json.load(f)

            current_id = data.get("id")

            # If missing OR duplicate → fix it
            if current_id is None or current_id in used_ids:
                new_id = get_next_free()
                data["id"] = new_id

                with open(file, "w") as f:
                    json.dump(data, f)

            else:
                used_ids.add(current_id)

        except Exception:
            continue


def load_json_index(start_id: int = 100):
    fix_json_id_conflicts(start_id)

    from pathlib import Path
    from fts.config import IN_PROGRESS_DIR
    import json

    result = {}
    used_ids = set()

    base = Path(IN_PROGRESS_DIR)
    if not base.exists():
        return result, start_id

    for file in base.glob("*.json"):
        try:
            with open(file, "r") as f:
                data = json.load(f)

            key = data.get("id")
            if key is None:
                continue

            result[key] = file
            used_ids.add(key)

        except Exception:
            continue

    # Find next free ID
    next_id = start_id
    while next_id in used_ids:
        next_id += 1

    return result, next_id