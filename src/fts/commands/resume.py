def cmd_resume(args, logger):
    commands = {
        "show": print_incomplete_transfers,
        "start": resume,
    }

    cmd = commands.get(args.subcommand)

    if cmd:
        cmd(args, logger)
    else:
        logger.error(f"Unknown subcommand: {args.subcommand}")


def resume(args, logger):
    return


def retrieve_incomplete_transfers():
    from pathlib import Path
    from fts.config import IN_PROGRESS_DIR
    import json

    base = Path(IN_PROGRESS_DIR)

    if not base.exists():
        return None  # signal missing dir

    incomplete = []

    for file in base.glob("*.json"):
        try:
            with open(file, "r") as f:
                data = json.load(f)

            transfer_id = str(data.get("id", "UNKNOWN"))
            dst = str(data.get("target", "unknown"))
            progress = data.get("progress", None)

            file_name = str(file.name.removesuffix(".json").removesuffix(".ftsdownload"))[:-17]

            prog = (
                f"~{round(progress, 1)}%" if isinstance(progress, (int, float))
                else "N/A"
            )

            incomplete.append({
                "id": transfer_id,
                "destination": dst,
                "progress": prog,
                "file": file_name
            })

        except Exception:
            continue

    return incomplete


def print_incomplete_transfers(args, logger):
    # --- ANSI colors ---
    RESET = "\033[0m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    CYAN = "\033[36m"
    DIM = "\033[2m"

    incomplete = retrieve_incomplete_transfers()

    if incomplete is None:
        print(f"{RED}No in-progress directory found.{RESET}")
        return

    if not incomplete:
        print(f"{GREEN}No incomplete transfers found.{RESET}")
        return

    # --- Column widths ---
    col_widths = {
        "id": max(len("ID"), *(len(t["id"]) for t in incomplete)),
        "file": max(len("FILE"), *(len(t["file"]) for t in incomplete)),
        "destination": max(len("DESTINATION"), *(len(t["destination"]) for t in incomplete)),
        "progress": max(len("PROGRESS"), *(len(t["progress"]) for t in incomplete)),
    }

    def pad(text, width):
        return text.ljust(width)

    def sep():
        return (
            f"+-{'-' * (col_widths['id'] - 1)}-"
            f"-+-{'-' * (col_widths['file'] - 1)}-"
            f"-+-{'-' * (col_widths['destination'] - 1)}-"
            f"-+-{'-' * (col_widths['progress'])}-+"
        )

    print(f"\n{CYAN}=== Incomplete Transfers ==={RESET}")
    print(sep())

    # Header
    print(
        f"| {CYAN}{pad('ID', col_widths['id'])}{RESET} "
        f"| {CYAN}{pad('FILE', col_widths['file'])}{RESET} "
        f"| {CYAN}{pad('DESTINATION', col_widths['destination'])}{RESET} "
        f"| {CYAN}{pad('PROGRESS', col_widths['progress'])}{RESET} |"
    )

    print(sep())

    # Rows
    for t in sorted(incomplete, key=lambda x: x["id"]):
        print(
            f"| {pad(t['id'], col_widths['id'])} "
            f"| {pad(t['file'], col_widths['file'])} "
            f"| {GREEN}{pad(t['destination'], col_widths['destination'])}{RESET} "
            f"| {YELLOW}{pad(t['progress'], col_widths['progress'])}{RESET} |"
        )

    print(sep())


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
