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
CONFIG_VERSION = 3

DEFAULTS = {
    "Core": {
        "CONFIG_VERSION": CONFIG_VERSION,
    },
    "Networking": {
        "DISCOVERY_PORT": 6064,
        "CHAT_PORT": 7064,
        "LIBRARY_PORT": 8064,
        "NOTEPAD_PORT": 9064,
        "IP_REMAPPING_WITH_MAC_ENABLED": "true",
    },
    "Storage": {
        "SAVE_DIR": os.path.expanduser("~/Downloads/fts"),
    },
    "Logging": {
        "VERBOSE_LOGGING_ENABLED": "true",
    },
    "Plugins": {
        "PLUGINS_ENABLED": "true",
    },
    "Library": {
        "LIBRARY_ENABLED": "false",
        "LIBRARY_IGNORE_HIDDEN_FOLDERS_ENABLED": "true",
    },
}
KEY_TO_SECTION = {
    key: section
    for section, values in DEFAULTS.items()
    for key in values.keys()
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

    for section, values in DEFAULTS.items():
        config[section] = {k: str(v) for k, v in values.items()}

    if backup:
        backup_config(CONFIG_PATH)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)

    return config



def migrate_config(config, old_version):
    # Remove deprecated legacy section
    if "Settings" in config:
        config.remove_section("Settings")

    for section, defaults in DEFAULTS.items():
        if section not in config:
            config[section] = {}

        for key, default in defaults.items():
            if key not in config[section]:
                config[section][key] = str(default)

    for section in list(config.sections()):
        if section not in DEFAULTS:
            config.remove_section(section)
            continue

        allowed = DEFAULTS[section].keys()
        for key in list(config[section].keys()):
            if key not in allowed:
                del config[section][key]


    config["Core"]["CONFIG_VERSION"] = str(CONFIG_VERSION)

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
            if "Core" not in config:
                broken_config = True
            else:
                current_config_version = int(
                    config["Core"].get("CONFIG_VERSION", 0)
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


def get_config_value(section: str, key: str):
    default = DEFAULTS[section][key]
    val = config[section].get(key, default)

    if isinstance(default, int):
        return int(val)

    if str(default).lower() in ("true", "false"):
        return str(val).lower() == "true"

    return val


def set_config_value(key: str, value):
    section = KEY_TO_SECTION.get(key)
    if section is None:
        raise KeyError(f"Unknown config key: {key}")

    if section not in config:
        config[section] = {}

    config[section][key] = str(value)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


# -----------------------------
# Apply Config Values
# -----------------------------
DISCOVERY_PORT = get_config_value("Networking", "DISCOVERY_PORT")
CHAT_PORT = get_config_value("Networking", "CHAT_PORT")
LIBRARY_PORT = get_config_value("Networking", "LIBRARY_PORT")
NOTEPAD_PORT = get_config_value("Networking", "NOTEPAD_PORT")
IP_REMAPPING_WITH_MAC = get_config_value("Networking", "IP_REMAPPING_WITH_MAC_ENABLED")

SAVE_DIR = get_config_value("Storage", "SAVE_DIR")

VERBOSE_LOGGING = get_config_value("Logging", "VERBOSE_LOGGING_ENABLED")

PLUGINS_ENABLED = get_config_value("Plugins", "PLUGINS_ENABLED")

LIBRARY_ENABLED = get_config_value("Library", "LIBRARY_ENABLED")
LIBRARY_IGNORE_HIDDEN_FOLDERS = get_config_value("Library", "LIBRARY_IGNORE_HIDDEN_FOLDERS_ENABLED")

# -----------------------------
# File Paths
# -----------------------------
SEEN_IPS_FILE = os.path.join(APP_DIR, "seen_ips.json")
CONTACTS_FILE = os.path.join(APP_DIR, "contacts.json")
LOG_FILE = os.path.join(APP_DIR, "log.txt")
DEBUG_FILE = os.path.join(APP_DIR, "debug.txt")
MUTED_FILE = os.path.join(APP_DIR, "muted.json")
CHAT_FILE = os.path.join(APP_DIR, "chat.json")
LOCK_FILE = os.path.join(APP_DIR, "lock.lock")
MAC_FILE = os.path.join(APP_DIR, "macs.json")

PLUGIN_DIR = os.path.join(APP_DIR, "plugins")

LOGS = [LOG_FILE]

# -----------------------------
# Logger Setup
# -----------------------------
logger = setup_logging(verbose=VERBOSE_LOGGING, id="APP", logfile=DEBUG_FILE)
