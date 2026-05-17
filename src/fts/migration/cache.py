import os
import shutil
from os.path import expanduser

from fts.cache import (
    CONFIG_FILE, PLUGINS_DIR, IN_PROGRESS_DIR,
    CERT_FILE, KEY_FILE, FINGERPRINT_FILE
)
from fts.app.cache import (
    CONFIG_FILE as APP_CONFIG_FILE,
    SEEN_IPS_FILE, MAC_FILE, MUTED_FILE,
    SECURE_PLUGIN_DIR,
    LOG_FILE, DEBUG_FILE, CHAT_FILE,
    CONTACTS_FILE, LIBRARY_CACHE_DIR
)

LEGACY_MAP = {
    # config
    "config.ini": CONFIG_FILE,
    "app/config.ini": APP_CONFIG_FILE,

    # logs
    "app/log.txt": LOG_FILE,
    "app/debug.txt": DEBUG_FILE,

    # state
    "app/seen_ips.json": SEEN_IPS_FILE,
    "app/macs.json": MAC_FILE,
    "app/muted.json": MUTED_FILE,
    "app/chat.json": CHAT_FILE,
    "app/contacts.json": CONTACTS_FILE,
    "known_servers.json": FINGERPRINT_FILE,

    # plugins
    "app/plugins": PLUGINS_DIR,

    # secure
    "app/plugins_secure": SECURE_PLUGIN_DIR,

    # library cache
    "app/library": LIBRARY_CACHE_DIR,

    # transfers
    "in_progress": IN_PROGRESS_DIR,

    # keys / cert
    "cert.pem": CERT_FILE,
    "key.pem": KEY_FILE,}

def migrate_legacy_files():
    """
    Moves legacy files/folders into new structure based on LEGACY_MAP.
    """


    base_dir = os.path.expanduser("~/.fts")

    # handle config backups
    migrate_config_backups(base_dir, "config.ini", CONFIG_FILE)
    migrate_config_backups(base_dir, "app/config.ini", APP_CONFIG_FILE)

    for legacy_path, new_path in LEGACY_MAP.items():
        src = os.path.join(base_dir, legacy_path)
        dst = new_path

        if not os.path.exists(src):
            continue

        # ensure destination parent exists
        os.makedirs(os.path.dirname(dst), exist_ok=True)

        try:
            # FILE → FILE
            if os.path.isfile(src):
                shutil.move(src, dst)

            # DIRECTORY → DIRECTORY
            elif os.path.isdir(src):
                # if destination exists, merge safely
                if os.path.exists(dst):
                    _merge_dirs(src, dst)
                    shutil.rmtree(src)
                else:
                    shutil.move(src, dst)

            print(f"[MIGRATED] {src} → {dst}")

        except Exception as e:
            print(f"[FAILED] {src} → {dst}: {e}\n\tThis may not be an issue.")

    backup_path = os.path.join(base_dir, "backup.zip")
    if os.path.exists(backup_path):
        new_backup_path = os.path.join(os.path.join(base_dir, "old\\", "backup.zip"))
        os.makedirs(os.path.dirname(new_backup_path), exist_ok=True)
        shutil.move(backup_path, new_backup_path)
        print(f"WARNING: cache backup cannot be migrated and will be left behind at:\n {new_backup_path}")
    _merge_dirs(os.path.join(base_dir, "app/"), os.path.join(base_dir, "old/"))



def migrate_config_backups(base_dir, legacy_key, new_path):
    """
    Moves config.ini.backup.* files correctly.
    """

    new_path = str(new_path)
    legacy_file = os.path.join(base_dir, legacy_key)
    legacy_dir = os.path.dirname(legacy_file)

    if not os.path.exists(legacy_dir):
        return

    for name in os.listdir(legacy_dir):
        if not name.startswith("config.ini.backup"):
            continue

        src = os.path.join(legacy_dir, name)

        # preserve suffix (.backup.1 etc)
        suffix = name.replace("config.ini", "")
        dst = new_path + suffix

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)

        print(f"[MIGRATED BACKUP] {src} → {dst}")


def _merge_dirs(src, dst):
    """
    Safely merges src into dst without breaking os.walk.
    Uses bottom-up traversal + copy semantics first.
    """

    for root, dirs, files in os.walk(src, topdown=False):
        rel = os.path.relpath(root, src)
        target_root = os.path.join(dst, rel) if rel != "." else dst

        os.makedirs(target_root, exist_ok=True)

        for f in files:
            src_file = os.path.join(root, f)
            dst_file = os.path.join(target_root, f)

            # move safely only after ensuring target exists
            if os.path.exists(dst_file):
                os.remove(dst_file)

            shutil.move(src_file, dst_file)

        # remove empty dirs safely
        if os.path.isdir(root) and not os.listdir(root):
            os.rmdir(root)

if __name__ == "__main__":
    migrate_legacy_files()