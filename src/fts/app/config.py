import configparser
import os

from fts.config import APP_DIR as app_dir
from fts.core.logger import setup_logging

# -----------------------------
# Default Configuration Values
# -----------------------------
save_dir_default = os.path.expanduser("~/Downloads/fts")
DEFAULTS = {
    "DISCOVERY_PORT": 6064,
    "CHAT_PORT": 7064,
    "LIBRARY_PORT": 8064,
    "SAVE_DIR": save_dir_default,
    "VERBOSE_LOGGING": "true",
    "PLUGINS_ENABLED": "true",
    "LIBRARY_ENABLED": "false",
}

# -----------------------------
# Setup Directories
# -----------------------------
APP_DIR = os.path.join(app_dir, "app")
os.makedirs(APP_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(APP_DIR, "config.ini")

# -----------------------------
# Create config.ini if missing
# -----------------------------
def create_default_config():
    config = configparser.ConfigParser()
    config["Settings"] = DEFAULTS
    with open(CONFIG_PATH, "w") as f:
        config.write(f)

if not os.path.exists(CONFIG_PATH):
    create_default_config()

# -----------------------------
# Load config.ini
# -----------------------------
config = configparser.ConfigParser()
config.read(CONFIG_PATH)

def get_config_value(key: str):
    """Return overridden value if present, with automatic type casting."""
    if "Settings" in config and key in config["Settings"]:
        val = config["Settings"][key]
    else:
        val = DEFAULTS[key]

    # Try to cast back to the right type
    default_val = DEFAULTS[key]
    if isinstance(default_val, int):
        try:
            return int(val)
        except ValueError:
            return default_val
    elif str(default_val).lower() in ("true", "false"):
        return str(val).lower() == "true"
    return val

def set_config_value(key: str, value):
    """Set a value in the Settings section and save the config."""

    # Ensure the section exists
    if "Settings" not in config:
        config.add_section("Settings")

    # ConfigParser only stores strings
    config["Settings"][key] = str(value)

    # Save back to disk
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        config.write(f)


# -----------------------------
# Apply Config Values
# -----------------------------
DISCOVERY_PORT = get_config_value("DISCOVERY_PORT")
CHAT_PORT = get_config_value("CHAT_PORT")
LIBRARY_PORT = get_config_value("LIBRARY_PORT")
SAVE_DIR = get_config_value("SAVE_DIR")
VERBOSE_LOGGING = get_config_value("VERBOSE_LOGGING")
PLUGINS_ENABLED = get_config_value("PLUGINS_ENABLED")
library_enabled = get_config_value("LIBRARY_ENABLED")


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
