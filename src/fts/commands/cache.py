import os
import shutil
import tempfile
import zipfile

from fts.config import IN_PROGRESS_DIR

EXCLUDE_DIRS = {"in_progress", "__pycache__", ".git"}

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
        "HASHES.SIG": "Used to verify plugins",
        "MACS.JSON": "Used to remap contact ips after ip change",
        "LIBRARY.JSON": "Cache for library tree to speed library construction time",
        "LIBRARY_LOG.JSON": "Log of all library requests",
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

    def get_dir_size(path):
        total = 0
        for root, dirs, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
        return total

    def _tree(current_path, prefix=""):
        odd = False
        entries = sorted(os.listdir(current_path))
        for i, entry in enumerate(entries):
            if ".lock" in entry:
                continue
            path = os.path.join(current_path, entry)
            connector = "└── " if i == len(entries) - 1 else "├── "

            if os.path.isdir(path):
                size = sizeof_fmt(get_dir_size(path))
                print(f"{Color.DIM}{prefix}{connector}{entry}/ ({Color.CYAN}{size}{Color.RESET}{Color.DIM}){Color.RESET}")
                _tree(path, prefix + ("    " if i == len(entries) - 1 else "│   "))
            else:
                odd = not odd
                size = sizeof_fmt(os.path.getsize(path))
                purpose = FILE_PURPOSES.get(entry.upper(), "Unknown purpose")
                lower_path = path.lower()
                if "Unknown" in purpose:
                    if "__pycache__" in lower_path:
                        purpose = "Cache file created by python"
                    elif "plugin" in lower_path:
                        purpose = "Used by a plugin"
                    elif "ini.backup" in lower_path:
                        purpose = "A backup of a config file after a config upgrade"
                    elif "in_progress" in lower_path:
                        if lower_path.endswith(".json"):
                            purpose = "Incomplete transfer entry"
                        if lower_path.endswith(".ftsdownload"):
                            purpose = "Incomplete transfer file"

                print(
                    f"{Color.DIM}{prefix}{connector}{Color.RESET}{entry} ({Color.RED}{size}{Color.RESET}) {Color.DIM}- {purpose}{Color.RESET}")

    print(f"{Color.BOLD}{APP_DIR}/{Color.RESET}")
    _tree(APP_DIR)
    size = sizeof_fmt(get_dir_size(APP_DIR))
    print(f"\n{Color.BOLD}Total cache size:{Color.RESET} {Color.GREEN}{size}{Color.RESET}")


def restore(args, logger):
    from fts.config import APP_DIR
    backup_path = os.path.join(APP_DIR, "backup.zip")

    if not os.path.exists(backup_path):
        logger.error(f"No backup found at '{backup_path}'")
        return

    logger.info(f"Restoring '{backup_path}'...")

    rollback_dir = None
    preserved_in_progress = None

    try:
        # Preserve in_progress
        in_progress_dir = os.path.join(APP_DIR, "in_progress")
        if os.path.exists(in_progress_dir):
            preserved_in_progress = tempfile.mkdtemp()
            shutil.copytree(
                in_progress_dir,
                os.path.join(preserved_in_progress, "in_progress")
            )
            logger.debug(f"Preserved in_progress directory: {os.path.join(preserved_in_progress, "in_progress")}")

        rollback_dir = tempfile.mkdtemp()

        # Copy backup to temp
        temp_backup = os.path.join(rollback_dir, "backup.zip")
        shutil.copy2(backup_path, temp_backup)
        logger.debug(f"Preserved backup.zip: {temp_backup}")


        # Rollback snapshot
        if os.path.exists(APP_DIR):
            shutil.copytree(APP_DIR, os.path.join(rollback_dir, "snapshot"))
        logger.debug(f"Rollback snapshot: {os.path.join(rollback_dir, "snapshot")}")


        # Purge
        clean(args, logger, level=99, yes=True)
        logger.info("Purged existing cache")

        # Restore archive
        with zipfile.ZipFile(temp_backup, 'r') as zipf:
            for member in zipf.infolist():

                name = member.filename.replace("\\", "/")

                if name.startswith("in_progress/"):
                    continue

                target_path = os.path.join(APP_DIR, *name.split("/"))

                # directory entry (robust check)
                if name.endswith("/"):
                    os.makedirs(target_path, exist_ok=True)
                    continue

                os.makedirs(os.path.dirname(target_path), exist_ok=True)

                with zipf.open(member, 'r') as source, open(target_path, 'wb') as target:
                    shutil.copyfileobj(source, target)

        logger.info(f"Restored backup into '{APP_DIR}'")

        # Restore in_progress back
        if preserved_in_progress:
            src = os.path.join(preserved_in_progress, "in_progress")
            dst = os.path.join(APP_DIR, "in_progress")

            if os.path.exists(dst):
                shutil.rmtree(dst)

            shutil.copytree(src, dst)
        logger.debug(f"Recached in_progress directory into '{APP_DIR}'")


        # Restore backup file itself
        shutil.copy2(temp_backup, os.path.join(APP_DIR, "backup.zip"))
        logger.debug(f"Recached backup.zip into '{APP_DIR}'")

    except Exception as e:
        import sys
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print(f"Error on line: {exc_tb.tb_lineno}")
        logger.error(f"Restore failed: {e}")

        try:
            # Rollback
            if rollback_dir:
                logger.info("Rollback started...")
                if os.path.exists(APP_DIR):
                    shutil.rmtree(APP_DIR)

                shutil.copytree(
                    os.path.join(rollback_dir, "snapshot"),
                    APP_DIR
                )

                logger.info("Rollback completed")
            else:
                logger.critical("Rollback failed: no snapshot available")
        except Exception as e:
            import sys
            logger.error(f"Rollback failed: {e}")


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
        logger.info(f"Backing up '{APP_DIR}'...")
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(APP_DIR):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for file in files:
                    # Skip the backup.zip file itself during zipping
                    if file == "backup.zip":
                        continue
                    if ".lock" in file:
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, APP_DIR)
                    zipf.write(file_path, arcname)
        logger.info(f"Created backup at '{backup_path}'\nReminder: Incomplete transfers are never backed up")
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
            f"and remove all incomplete transfers,\n"
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
