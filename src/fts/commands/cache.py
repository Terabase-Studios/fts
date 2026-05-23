import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from fts.app.cache import (
    CHAT_FILE,
    CONTACTS_FILE,
    DEBUG_FILE,
    HASHES_JSON,
    HASHES_SIG,
    LIBRARY_CACHE_DIR,
    LIBRARY_CACHE_FILE,
    LIBRARY_LOG_FILE,
    LOG_FILE,
    MAC_FILE,
    MUTED_FILE,
    PLUGIN_DIR,
    SECURE_PLUGIN_DIR,
    SEEN_IPS_FILE,
    CONFIG_FILE as APP_CONFIG_FILE,
)
from fts.cache import (
    ALIASES_FILE,
    CACHE_DIR,
    CERT_FILE,
    CONFIG_DIR,
    CONFIG_FILE,
    DATA_DIR,
    FINGERPRINT_FILE,
    IN_PROGRESS_DIR,
    KEY_FILE,
    LOGS_DIR,
    PLUGINS_DIR,
    RECEIVING_PID,
    STATE_DIR,
    ensure_dir,
)
from fts.migration.cache import LEGACY_MAP

EXCLUDE_DIRS = {"in_progress", "__pycache__", ".git"}
BACKUP_NAME = "backup.zip"

STORAGE_ROOTS = {
    "config": Path(CONFIG_DIR),
    "cache": Path(CACHE_DIR),
    "state": Path(STATE_DIR),
    "logs": Path(LOGS_DIR),
    "data": Path(DATA_DIR),
}

MANAGED_PATHS = {
    "config": [
        CONFIG_FILE,
        APP_CONFIG_FILE,
        CONTACTS_FILE,
        MUTED_FILE,
        MAC_FILE,
        FINGERPRINT_FILE,
        ALIASES_FILE,
        PLUGIN_DIR,
        PLUGINS_DIR,
        SECURE_PLUGIN_DIR,
    ],
    "cache": [
        LIBRARY_CACHE_DIR,
    ],
    "state": [
        SEEN_IPS_FILE,
        CHAT_FILE,
        IN_PROGRESS_DIR,
        RECEIVING_PID,
    ],
    "logs": [
        LOG_FILE,
        DEBUG_FILE,
    ],
    "data": [
        CERT_FILE,
        KEY_FILE,
    ],
}

FILE_PURPOSES = {
    "LOG.TXT": "History of transfers",
    "DEBUG.TXT": "Debug log file",
    "CHAT.JSON": "Stored chat history",
    "SEEN_IPS.JSON": "Seen IP addresses for offline display",
    "CONTACTS.JSON": "IP to Contact dict",
    "MUTED.JSON": "Muted users list",
    "CONFIG.INI": "Configuration file",
    "APP_CONFIG.INI": "App configuration file",
    "ALIASES.JSON": "Command line aliases",
    "CERT.PEM": "FTS certificate",
    "KEY.PEM": "FTS private key",
    "KNOWN_SERVERS.JSON": "Trusted server ip fingerprints",
    "FTS_RECEIVER.PID": "PID of the detached server",
    "BACKUP.ZIP": "Backup of the cache for 'fts cache restore'",
    "HASHES.JSON": "Used to verify plugins",
    "HASHES.SIG": "Used to verify plugins",
    "MACS.JSON": "Used to remap contact ips after ip change",
    "LIBRARY.JSON": "Cache for library tree to speed library construction time",
    "LIBRARY_LOG.JSON": "Log of all library requests",
}


def cmd_cache(args, logger):
    commands = {
        "show": show,
        "backup": backup,
        "restore": restore,
        "clean": clean,
    }

    cmd = commands.get(args.subcommand)

    if cmd:
        cmd(args, logger)
    else:
        logger.error(f"Unknown subcommand: {args.subcommand}")


def backup_path():
    return Path(CACHE_DIR) / BACKUP_NAME


def legacy_backup_paths():
    legacy_root = Path.home() / ".fts"
    return [
        legacy_root / BACKUP_NAME,
        legacy_root / "old" / BACKUP_NAME,
    ]


def _find_backup_path():
    current = backup_path()
    if current.exists():
        return current

    for path in legacy_backup_paths():
        if path.exists():
            return path

    return current


def _valid_zip_parts(name):
    parts = PurePosixPath(name.replace("\\", "/")).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    return parts


def _is_relative_to(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _top_level_roots():
    roots = []

    for root in sorted(set(STORAGE_ROOTS.values()), key=lambda p: len(p.resolve().parts)):
        if any(root.resolve() == existing.resolve() or _is_relative_to(root, existing) for existing in roots):
            continue
        roots.append(root)

    return roots


def _backup_members():
    seen = set()

    for label, paths in MANAGED_PATHS.items():
        root = STORAGE_ROOTS[label]
        if not root.exists():
            continue

        for path in paths:
            path = Path(path)
            if not path.exists() or path.name in EXCLUDE_DIRS:
                continue

            if path.is_file():
                resolved = path.resolve()
                if resolved in seen or path == backup_path() or ".lock" in path.name:
                    continue
                seen.add(resolved)
                yield path, str(PurePosixPath(label) / path.relative_to(root).as_posix())
                continue

            for current_root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

                for file in files:
                    if ".lock" in file:
                        continue

                    file_path = Path(current_root) / file
                    resolved = file_path.resolve()
                    if resolved in seen or file_path == backup_path():
                        continue

                    seen.add(resolved)
                    arcname = PurePosixPath(label) / file_path.relative_to(root).as_posix()
                    yield file_path, str(arcname)


def _managed_entries(label):
    root = STORAGE_ROOTS[label]
    entries = []
    seen = set()

    if not root.exists():
        return entries

    for path in MANAGED_PATHS[label]:
        path = Path(path)
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if not path.exists():
            continue

        top = root / relative.parts[0]
        resolved = top.resolve()
        if resolved in seen:
            continue

        seen.add(resolved)
        entries.append(top)

    return sorted(entries, key=lambda p: p.name.lower())


def _legacy_target(parts):
    legacy_keys = sorted(LEGACY_MAP, key=len, reverse=True)

    for legacy_key in legacy_keys:
        key_parts = PurePosixPath(legacy_key).parts
        if tuple(parts[:len(key_parts)]) != key_parts:
            continue

        target = Path(LEGACY_MAP[legacy_key])
        suffix = parts[len(key_parts):]
        return target.joinpath(*suffix)

    return None


def _restore_target(name):
    parts = _valid_zip_parts(name)
    if not parts:
        return None

    root = STORAGE_ROOTS.get(parts[0])
    if root is not None:
        if len(parts) == 1:
            return None
        target = root.joinpath(*parts[1:])
        return target if _is_relative_to(target, root) else None

    target = _legacy_target(parts)
    if target is None:
        return None

    known_roots = tuple(STORAGE_ROOTS.values())
    return target if any(_is_relative_to(target, root) for root in known_roots) else None


def show(args, logger):
    class Color:
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        CYAN = "\033[96m"
        GREEN = "\033[92m"
        RED = "\033[91m"

    def sizeof_fmt(num, suffix="B"):
        for unit in ["", "K", "M", "G", "T", "P"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}P{suffix}"

    def get_dir_size(path):
        total = 0
        if not path.exists():
            return total

        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                fp = Path(root) / f
                if fp.exists():
                    total += fp.stat().st_size
        return total

    def _purpose(path):
        purpose = FILE_PURPOSES.get(path.name.upper(), "Unknown purpose")
        lower_path = str(path).lower()

        if "Unknown" not in purpose:
            return purpose
        if "__pycache__" in lower_path:
            return "Cache file created by python"
        if "plugin" in lower_path:
            return "Used by a plugin"
        if "ini.backup" in lower_path:
            return "A backup of a config file after a config upgrade"
        if "in_progress" in lower_path and lower_path.endswith(".json"):
            return "Incomplete transfer entry"
        if "in_progress" in lower_path and lower_path.endswith(".ftsdownload"):
            return "Incomplete transfer file"
        return purpose

    def _tree(current_path, prefix=""):
        if not current_path.exists():
            return

        entries = sorted(entry for entry in current_path.iterdir() if ".lock" not in entry.name)
        for i, path in enumerate(entries):
            _print_entry(path, prefix, i == len(entries) - 1)

    def _print_entry(path, prefix, is_last):
        connector = "`-- " if is_last else "+-- "

        if path.is_dir():
            size = sizeof_fmt(get_dir_size(path))
            print(
                f"{Color.DIM}{prefix}{connector}{path.name}/ ({Color.CYAN}{size}{Color.RESET}{Color.DIM}){Color.RESET}"
            )
            _tree(path, prefix + ("    " if is_last else "|   "))
        else:
            size = sizeof_fmt(path.stat().st_size)
            print(
                f"{Color.DIM}{prefix}{connector}{Color.RESET}{path.name} ({Color.RED}{size}{Color.RESET}) "
                f"{Color.DIM}- {_purpose(path)}{Color.RESET}"
            )

    total = 0
    for label, root in STORAGE_ROOTS.items():
        print(f"{Color.BOLD}{label}: {root}/{Color.RESET}")
        entries = _managed_entries(label)
        if entries:
            for i, entry in enumerate(entries):
                _print_entry(entry, "", i == len(entries) - 1)
        elif not root.exists():
            print(f"{Color.DIM}`-- missing{Color.RESET}")
        else:
            print(f"{Color.DIM}`-- empty{Color.RESET}")
        total += sum(get_dir_size(entry) if entry.is_dir() else entry.stat().st_size for entry in entries)

    print(f"\n{Color.BOLD}Total cache size:{Color.RESET} {Color.GREEN}{sizeof_fmt(total)}{Color.RESET}")


def restore(args, logger):
    source_backup = _find_backup_path()

    if not source_backup.exists():
        logger.error(f"No backup found at '{source_backup}'")
        return

    logger.info(f"Restoring '{source_backup}'...")

    rollback_dir = None
    preserved_in_progress = None
    snapshot_roots = []

    try:
        if Path(IN_PROGRESS_DIR).exists():
            preserved_in_progress = Path(tempfile.mkdtemp()) / "in_progress"
            shutil.copytree(IN_PROGRESS_DIR, preserved_in_progress)
            logger.debug(f"Preserved in_progress directory: {preserved_in_progress}")

        rollback_dir = Path(tempfile.mkdtemp())
        temp_backup = rollback_dir / BACKUP_NAME
        shutil.copy2(source_backup, temp_backup)
        logger.debug(f"Preserved backup.zip: {temp_backup}")

        snapshot_dir = rollback_dir / "snapshot"
        for i, root in enumerate(_top_level_roots()):
            if root.exists():
                snapshot_path = snapshot_dir / f"root_{i}"
                shutil.copytree(root, snapshot_path)
                snapshot_roots.append((root, snapshot_path))
        logger.debug(f"Rollback snapshot: {snapshot_dir}")

        clean(args, logger, level=99, yes=True)
        logger.info("Purged existing cache")

        with zipfile.ZipFile(temp_backup, "r") as zipf:
            for member in zipf.infolist():
                target_path = _restore_target(member.filename)
                if target_path is None:
                    logger.debug(f"Skipped unknown backup member: {member.filename}")
                    continue

                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zipf.open(member, "r") as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)

        if preserved_in_progress:
            dst = Path(IN_PROGRESS_DIR)
            if dst.exists():
                shutil.rmtree(dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(preserved_in_progress, dst)
            logger.debug(f"Recached in_progress directory into '{dst}'")

        ensure_dir(Path(CACHE_DIR))
        shutil.copy2(temp_backup, backup_path())
        logger.debug(f"Recached backup.zip into '{backup_path()}'")
        logger.info("Restore completed")

    except Exception as e:
        logger.error(f"Restore failed: {e}")

        try:
            if not rollback_dir:
                logger.critical("Rollback failed: no snapshot available")
                return

            logger.info("Rollback started...")
            for root in _top_level_roots():
                if root.exists():
                    shutil.rmtree(root)

            for root, src in snapshot_roots:
                if src.exists():
                    root.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(src, root)

            logger.info("Rollback completed")
        except Exception as rollback_error:
            logger.error(f"Rollback failed: {rollback_error}")


def backup(args, logger):
    ensure_dir(Path(CACHE_DIR))
    destination = backup_path()

    if destination.exists() and not args.yes:
        confirm = input(f"A backup already exists at '{destination}'.\nReplace it? (yes/[no]): ")
        if confirm.lower() != "yes":
            logger.info("Backup cancelled by user.")
            return

    try:
        logger.info("Backing up FTS storage directories...")
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path, arcname in _backup_members():
                zipf.write(file_path, arcname)
        logger.info(f"Created backup at '{destination}'\nReminder: Incomplete transfers are never backed up")
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")


def clean(args, logger, level=-1, yes=False):
    levels = {"clean": 0, "clear": 1, "reset": 2, "purge": 3}
    if level == -1:
        level = levels.get(args.level)

    if level is None:
        logger.error(f"Unknown level: {args.level}")
        return

    if level >= 3 and not args.yes and not yes:
        confirm = input(
            f"WARNING: This will delete the FTS backup cache if it exists,\n"
            f"and remove all incomplete transfers,\n"
            f"and remove your current FTS key and certificate,\n"
            f"and any FTS users who previously sent you files will need to manually re-trust you.\n"
            f"Type 'yes' to confirm: "
        )
        if confirm.lower() != "yes":
            logger.info("Aborted by user.")
            return

    def safe_remove(path):
        path = Path(path)
        if not path.exists():
            return
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            logger.debug(f"Removed '{path}'")
        except PermissionError:
            logger.error(f"Permission denied for '{path}'.\nMake sure all instances of fts-tool are closed.")
        except Exception as e:
            logger.error(f"Failed to remove '{path}': {e}")

    if level >= 0:
        for f in [LOG_FILE, SEEN_IPS_FILE, CHAT_FILE]:
            safe_remove(f)

    if level >= 1:
        try:
            from fts.app.config import logger as app_logger

            for handler in app_logger.handlers[:]:
                app_logger.removeHandler(handler)
                handler.close()
        except (ModuleNotFoundError, ImportError, AttributeError):
            pass

        for f in [DEBUG_FILE, CONTACTS_FILE, MUTED_FILE]:
            safe_remove(f)

    if level >= 2:
        for f in [
            APP_CONFIG_FILE,
            PLUGIN_DIR,
            PLUGINS_DIR,
            SECURE_PLUGIN_DIR,
            HASHES_JSON,
            HASHES_SIG,
            LIBRARY_CACHE_DIR,
            LIBRARY_CACHE_FILE,
            LIBRARY_LOG_FILE,
            MAC_FILE,
            CONFIG_FILE,
            ALIASES_FILE,
            FINGERPRINT_FILE,
            IN_PROGRESS_DIR,
        ]:
            safe_remove(f)

    if level >= 3:
        for f in [RECEIVING_PID, CERT_FILE, KEY_FILE]:
            safe_remove(f)
        for root in STORAGE_ROOTS.values():
            safe_remove(root)
