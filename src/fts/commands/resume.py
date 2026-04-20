import os
from argparse import Namespace

from fts.core.aliases import resolve_args


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
    transfers = filter_in_progress(retrieve_incomplete_transfers())
    target_transfer = None
    transfer_json = None
    for transfer in transfers:
        if transfer["id"] == str(args.id):
            target_transfer = transfer["complete"]
            transfer_json = transfer["path"]
            break

    if not target_transfer:
        logger.error(f"Incomplete transfer not found")
        return
    elif target_transfer["type"] == "receive":
        logger.error(f"Transfers must be resumed by sender")
        return

    args = Namespace(
        path=target_transfer["metadata"]["source_path"],
        ip=target_transfer["target"],
        limit=args.limit,
        port=0 if args.port == -1 else args.port,
        progress=args.progress,
        name=target_transfer["metadata"]["name"],
        nocompress=not target_transfer["metadata"]["compressed"],
        autotrust=True
    )
    from fts.commands.sender import cmd_send
    cmd_send(resolve_args(args, logger), logger, resume=transfer_json, override_compress= "y" if target_transfer["metadata"]["compressed"] else "n")


def filter_in_progress(transfers):
    filtered_transfers = []
    for transfer in transfers:
        if transfer.get("in_progress"):
            continue
        filtered_transfers.append(transfer)
    return filtered_transfers


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
            type = data.get("type", "UNKNOWN")
            dst = str(data.get("target", "unknown"))
            progress = data.get("progress", None)
            in_progress = os.path.exists(str(file) + ".lock")

            file_name = str(file.name.removesuffix(".json").removesuffix(".ftsdownload"))[:-17]

            prog = (
                f"~{round(progress, 1)}%" if isinstance(progress, (int, float))
                else "N/A"
            )

            incomplete.append({
                "id": transfer_id,
                "type": type,
                "destination": dst,
                "progress": prog,
                "file": file_name,
                "in_progress": in_progress,
                "complete": data,
                "path": file
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
    BOLD = "\033[1m"

    incomplete = filter_in_progress(retrieve_incomplete_transfers())

    if incomplete is None:
        print(f"{RED}No in-progress directory found.{RESET}")
        return

    if not incomplete:
        print(f"{GREEN}No incomplete transfers found.{RESET}")
        return

    # --- Split by type ---
    send_transfers = [t for t in incomplete if t.get("type") == "send"]
    recv_transfers = [t for t in incomplete if t.get("type") == "receive"]

    # --- Combine (SEND first, RECEIVE last) ---
    ordered = sorted(send_transfers, key=lambda x: x["id"]) + \
              sorted(recv_transfers, key=lambda x: x["id"])

    # --- Column widths ---
    col_widths = {
        "id": max(len("ID"), *(len(t["id"]) for t in ordered)),
        "file": max(len("FILE"), *(len(t["file"]) for t in ordered)),
        "destination": max(len("DESTINATION"), *(len(t["destination"]) for t in ordered)),
        "progress": max(len("PROGRESS"), *(len(t["progress"]) for t in ordered)),
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

    # --- Top message ---
    print(f"\n{CYAN}=== Incomplete Transfers ==={RESET}")
    print(f"{BOLD}{GREEN}SEND transfers can be resumed if destination has a server up{RESET}")
    print(f"{BOLD}{RED}RECEIVE transfers are view-only and must be resumed by the sender{RESET}")

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
    for t in ordered:
        is_send = t.get("type") == "send"

        file_color = GREEN if is_send else DIM
        dest_color = GREEN if is_send else DIM
        prog_color = YELLOW if is_send else DIM

        print(
            f"| {pad(t['id'], col_widths['id'])} "
            f"| {file_color}{pad(t['file'], col_widths['file'])}{RESET} "
            f"| {dest_color}{pad(t['destination'], col_widths['destination'])}{RESET} "
            f"| {prog_color}{pad(t['progress'], col_widths['progress'])}{RESET} |"
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
