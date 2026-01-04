import os
import shutil
import tempfile
import zipfile


def cmd_cache(args, logger):
    match args.subcommand:
        case "show":
            show()
        case "backup":
            backup(args, logger)
        case "restore":
            restore(args, logger)
        case "clean":
            clean(args, logger)
        case _:
            logger.error(f"Unknown subcommand : {args.subcommand}")


def show():
    from fts.config import APP_DIR
    FILE_PURPOSES = {
        "LOG.TXT": "History of transfers",
        "DEBUG.TXT": "Debug log file",
        "CHAT.JSON": "Stored chat history",
        "SEEN_IPS.JSON": "Seen IP addresses for offline display",
        "CONTACTS.JSON": "IP to Contact dict",
        "MUTED.JSON": "Muted users list",
        "CONFIG.INI": "Configuration file",
        "ALIASES.JSON": "Command line aliases",
        "CERT.PEM": "FTS certificate",
        "KEY.PEM": "FTS private key",
        "KNOWN_SERVERS.JSON": "Trusted server ip fingerprints",
        "FTS_RECEIVER.PID": "PID of the detached server",
        "BACKUP.ZIP": "Backup of the cache for \'fts cache restore\'",
        "HASHES.JSON": "Used to verify plugins",
        "HASHES.SIG": "Used to verify plugins"
    }

    class Color:
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        BLUE = "\033[94m"
        CYAN = "\033[96m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        MAGENTA = "\033[95m"
        GRAY = "\033[37m"

    def sizeof_fmt(num, suffix="B"):
        """Convert bytes to human-readable string."""
        for unit in ["", "K", "M", "G", "T", "P"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}P{suffix}"

    def _tree(current_path, prefix=""):
        odd = False
        entries = sorted(os.listdir(current_path))
        for i, entry in enumerate(entries):
            if ".lock" in entry:
                continue
            path = os.path.join(current_path, entry)
            connector = "└── " if i == len(entries) - 1 else "├── "

            if os.path.isdir(path):
                print(f"{Color.DIM}{prefix}{connector}{entry}/{Color.RESET}")
                _tree(path, prefix + ("    " if i == len(entries) - 1 else "│   "))
            else:
                odd = not odd
                size = sizeof_fmt(os.path.getsize(path))
                purpose = FILE_PURPOSES.get(entry.upper(), "Unknown purpose")
                print(f"{Color.DIM}{prefix}{connector}{Color.RESET}{entry} ({Color.RED}{size}{Color.RESET}) - {purpose}")

    print(f"{Color.BOLD}{APP_DIR}/{Color.RESET}")
    _tree(APP_DIR)


def restore(args, logger):
    from fts.config import APP_DIR
    backup_path = os.path.join(APP_DIR, "backup.zip")

    if not os.path.exists(backup_path):
        logger.error(f"No backup found at '{backup_path}'")
        return

    # Create temporary directory for restore
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_backup = os.path.join(temp_dir, "backup.zip")
        try:
            # Copy backup to temp
            shutil.copy2(backup_path, temp_backup)
            logger.debug(f"Copied backup to temporary location '{temp_backup}'")

            # Make a rollback copy of current APP_DIR in temp
            rollback_dir = os.path.join(temp_dir, "rollback")
            if os.path.exists(APP_DIR):
                shutil.copytree(APP_DIR, rollback_dir)
                logger.debug(f"Created rollback copy at '{rollback_dir}'")

            # Purge current cache completely
            clean(args, logger, level=99, yes=True)
            logger.info("Purged existing .fts cache")

            # Unzip backup into APP_DIR
            with zipfile.ZipFile(temp_backup, 'r') as zipf:
                zipf.extractall(APP_DIR)
            logger.info(f"Restored backup into '{APP_DIR}'")

            # Copy backup back into APP_DIR to keep it
            shutil.copy2(temp_backup, os.path.join(APP_DIR, "backup.zip"))
            logger.debug("Backup copied back into APP_DIR")

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            # Rollback
            if os.path.exists(rollback_dir):
                if os.path.exists(APP_DIR):
                    shutil.rmtree(APP_DIR)
                shutil.copytree(rollback_dir, APP_DIR)
                logger.info("Rollback completed, restored previous state")
            else:
                logger.error("Rollback failed: no previous state saved")


def backup(args, logger):
    from fts.config import APP_DIR
    if not os.path.exists(APP_DIR):
        logger.error(f".fts directory not found at '{APP_DIR}'")
        return

    backup_path = os.path.join(APP_DIR, "backup.zip")

    # Check if backup already exists
    if os.path.exists(backup_path) and not args.yes:
        confirm = input(f"A backup already exists at '{backup_path}'.\nReplace it? (yes/[no]): ")
        if confirm.lower() != "yes":
            logger.info("Backup cancelled by user.")
            return

    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(APP_DIR):
                for file in files:
                    # Skip the backup.zip file itself during zipping
                    if file == "backup.zip":
                        continue
                    if ".lock" in file:
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, APP_DIR)
                    zipf.write(file_path, arcname)
        logger.info(f"Created backup at '{backup_path}'")
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")


def clean(args, logger, level=-1, yes=False):
    app_found = True
    try:
        from fts.app.config import APP_DIR as TUI_APP_DIR
        from fts.app.config import CONFIG_PATH as APP_CONFIG_PATH
        from fts.app.config import (SEEN_IPS_FILE, CONTACTS_FILE, LOG_FILE,
                                    DEBUG_FILE, MUTED_FILE, CHAT_FILE, LOCK_FILE,
                                    PLUGIN_DIR)
    except (ModuleNotFoundError, ImportError):
        app_found = False

    from fts.config import APP_DIR, ALIASES_FILE, RECEIVING_PID, CERT_FILE, KEY_FILE, FINGERPRINT_FILE, CONFIG_FILE

    levels = {"clean": 0, "clear": 1, "reset": 2, "purge": 3}
    if level == -1:
        level = levels.get(args.level)

    if level is None:
        logger.error(f"Unknown level: {args.level}")
        return

    # Purge warning
    if level >= 3 and not args.yes and not yes:
        confirm = input(
            f"WARNING: This will delete the FTS backup cache if it exists,\n"
            f"and remove your current FTS key and certificate,\n"
            f"and any FTS users who previously sent you files will need to manually re-trust you.\n"
            f"Type 'yes' to confirm: "
        )
        if confirm.lower() != "yes":
            logger.info("Aborted by user.")
            return

    def safe_remove(path):
        """Remove file or directory safely."""
        if not os.path.exists(path):
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            logger.debug(f"Removed '{path}'")
        except PermissionError:
            logger.error(f"Permission denied for '{path}'.\nMake sure all instances of fts-tool are closed.")
        except Exception as e:
            logger.error(f"Failed to remove '{path}': {e}")

    # Level 0: clean
    if level >= 0 and app_found:
        for f in [LOG_FILE, SEEN_IPS_FILE, CHAT_FILE]:
            safe_remove(f)

    # Level 1: clear
    if level >= 1 and app_found:
        from fts.app.config import logger as app_logger
        # Remove handlers to clean up resources
        for handler in app_logger.handlers[:]:
            app_logger.removeHandler(handler)
            handler.close()
        del app_logger

        for f in [DEBUG_FILE, CONTACTS_FILE, MUTED_FILE]:
            safe_remove(f)

    # Level 2: reset
    if level >= 2:
        if app_found:
            for f in [APP_CONFIG_PATH, PLUGIN_DIR, TUI_APP_DIR]:
                safe_remove(f)
        for f in [CONFIG_FILE, ALIASES_FILE, FINGERPRINT_FILE]:
            safe_remove(f)

    # Level 3: purge
    if level >= 3:
        for f in [RECEIVING_PID, CERT_FILE, KEY_FILE]:
            safe_remove(f)
        safe_remove(APP_DIR)

