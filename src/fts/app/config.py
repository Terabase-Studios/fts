import os
import configparser
from fts.config import APP_DIR as app_dir
from fts.core.logger import setup_logging
from pathlib import Path

# -----------------------------
# Default Configuration Values
# -----------------------------
save_dir_default = os.path.expanduser("~/Downloads/fts")
DEFAULTS = {
    "DISCOVERY_PORT": 6064,
    "CHAT_PORT": 7064,
    "SAVE_DIR": save_dir_default,
    "VERBOSE_LOGGING": "true"
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

# -----------------------------
# Apply Config Values
# -----------------------------
DISCOVERY_PORT = get_config_value("DISCOVERY_PORT")
CHAT_PORT = get_config_value("CHAT_PORT")
SAVE_DIR = get_config_value("SAVE_DIR")
VERBOSE_LOGGING = get_config_value("VERBOSE_LOGGING")

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

LOGS = [LOG_FILE]

# -----------------------------
# Logger Setup
# -----------------------------
logger = setup_logging(verbose=VERBOSE_LOGGING, id="APP", logfile=DEBUG_FILE)
