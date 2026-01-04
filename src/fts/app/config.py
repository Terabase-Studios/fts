import configparser
import os
import time

from fts.config import APP_DIR as app_dir, EXPERIMENTAL_FEATURES_ENABLED
from fts.core.logger import setup_logging

# -----------------------------
# Base FTS Configuration Values
# -----------------------------
EXPERIMENTAL_FEATURES_ENABLED = EXPERIMENTAL_FEATURES_ENABLED

# -----------------------------
# Default Configuration Values
# -----------------------------
save_dir_default = os.path.expanduser("~/Downloads/fts")
CONFIG_VERSION = 1

DEFAULTS = {
    "CONFIG_VERSION": CONFIG_VERSION,

    "DISCOVERY_PORT": 6064,
    "CHAT_PORT": 7064,
    "LIBRARY_PORT": 8064,
    "NOTEPAD_PORT": 9064,

    "SAVE_DIR": os.path.expanduser("~/Downloads/fts"),
    "VERBOSE_LOGGING": "true",
    "PLUGINS_ENABLED": "true",
    "LIBRARY_ENABLED": "false",
    "LIBRARY_IGNORE_HIDDEN_FOLDERS": "true",
}
# -----------------------------
# Setup Directories
# -----------------------------
APP_DIR = os.path.join(app_dir, "app")
os.makedirs(APP_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(APP_DIR, "config.ini")

def backup_config(path):
    if not os.path.exists(path):
        return

    base = path + ".backup"
    i = 1
    while True:
        candidate = f"{base}.{i}" if i else base
        if not os.path.exists(candidate + ".txt"):
            os.rename(path, candidate + ".txt")
            break
        i += 1

def resave_config(backup=True):
    config = configparser.ConfigParser()
    config["Settings"] = {k: str(v) for k, v in DEFAULTS.items()}

    if backup:
        backup_config(CONFIG_PATH)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)

    return config

def migrate_config(config, old_version):
    settings = config["Settings"]

    # add new defaults without overwriting user values
    for key, default in DEFAULTS.items():
        if key not in settings:
            settings[key] = str(default)

    # bump version
    settings["CONFIG_VERSION"] = str(CONFIG_VERSION)

    backup_config(CONFIG_PATH)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)

    return config

def load_or_create_config():
    config = configparser.ConfigParser()
    broken_config = False
    current_config_version = 0

    if os.path.exists(CONFIG_PATH):
        try:
            config.read(CONFIG_PATH)
            if "Settings" not in config:
                broken_config = True
            else:
                current_config_version = int(
                    config["Settings"].get("CONFIG_VERSION", 0)
                )
        except Exception as e:
            print(f"ERROR: failed to load {CONFIG_PATH}: {e}")
            broken_config = True
    else:
        return resave_config(False)

    if broken_config:
        print("INFO: Recreating config.ini with default settings, a backup will be saved in the same directory.")
        return resave_config()

    if CONFIG_VERSION != current_config_version:
        print("INFO: Migrating config.ini to a new config version, a backup will be saved in the same directory.")
        time.sleep(1)
        return migrate_config(config, current_config_version)

    return config


config = load_or_create_config()

def get_config_value(key: str):
    val = config["Settings"].get(key, DEFAULTS[key])
    default = DEFAULTS[key]

    if isinstance(default, int):
        return int(val)
    if str(default).lower() in ("true", "false"):
        return str(val).lower() == "true"
    return val

def set_config_value(key: str, value):
    config["Settings"][key] = str(value)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


# -----------------------------
# Apply Config Values
# -----------------------------
DISCOVERY_PORT = get_config_value("DISCOVERY_PORT")
CHAT_PORT = get_config_value("CHAT_PORT")
LIBRARY_PORT = get_config_value("LIBRARY_PORT")
NOTEPAD_PORT = get_config_value("NOTEPAD_PORT")
SAVE_DIR = get_config_value("SAVE_DIR")
VERBOSE_LOGGING = get_config_value("VERBOSE_LOGGING")
PLUGINS_ENABLED = get_config_value("PLUGINS_ENABLED")
library_enabled = get_config_value("LIBRARY_ENABLED")
LIBRARY_IGNORE_HIDDEN_FOLDERS = get_config_value("LIBRARY_IGNORE_HIDDEN_FOLDERS")


# -----------------------------
# File Paths
# -----------------------------
SEEN_IPS_FILE = os.path.join(APP_DIR, "seen_ips.json")
CONTACTS_FILE = os.path.join(APP_DIR, "contacts.json")
LOG_FILE      = os.path.join(APP_DIR, "log.txt")
DEBUG_FILE    = os.path.join(APP_DIR, "debug.txt")
MUTED_FILE    = os.path.join(APP_DIR, "muted.json")
CHAT_FILE     = os.path.join(APP_DIR, "chat.json")
LOCK_FILE     = os.path.join(APP_DIR, "lock.lock")

PLUGIN_DIR    = os.path.join(APP_DIR, "plugins")


LOGS = [LOG_FILE]


# -----------------------------
# Logger Setup
# -----------------------------
logger = setup_logging(verbose=VERBOSE_LOGGING, id="APP", logfile=DEBUG_FILE)
