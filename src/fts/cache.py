from pathlib import Path
from platformdirs import PlatformDirs

dirs = PlatformDirs("Fts-Tool", "Terabase")

BASE_CONFIG = Path(dirs.user_config_dir)
BASE_CACHE = Path(dirs.user_cache_dir)
BASE_STATE = Path(dirs.user_state_dir)
BASE_LOGS = Path(dirs.user_log_dir)
BASE_DOWNLOAD = Path(dirs.user_downloads_dir)
BASE_DATA = Path(dirs.user_data_dir)

def ensure_root_dir(path: Path):
    if path.exists() and path.is_file():
        path.unlink()  # remove broken file
    path.mkdir(parents=True, exist_ok=True)

for base in [BASE_CONFIG, BASE_CACHE, BASE_STATE, BASE_LOGS, BASE_DOWNLOAD, BASE_DATA]:
    ensure_root_dir(base)

CONFIG_DIR = BASE_CONFIG
CACHE_DIR = BASE_CACHE
STATE_DIR = BASE_STATE
LOGS_DIR = BASE_LOGS
DOWNLOAD_DIR = BASE_DOWNLOAD
DATA_DIR = BASE_DATA

# ----------------------------
# Plugins
# ----------------------------
PLUGINS_DIR = CONFIG_DIR / "plugins"
PLUGIN_DATA_DIR = DATA_DIR / "plugins"

# ----------------------------
# STATE (runtime + transfers)
# ----------------------------
IN_PROGRESS_DIR = STATE_DIR / "in_progress"
RECEIVING_PID = STATE_DIR / "fts_receiver.pid"

# ----------------------------
# SECURITY (IMPORTANT)
# ----------------------------
CERT_FILE = DATA_DIR / "cert.pem"
KEY_FILE = DATA_DIR / "key.pem"

# ----------------------------
# CONFIG (user rules / identity)
# ----------------------------
CONFIG_FILE = CONFIG_DIR / "config.ini"
FINGERPRINT_FILE = CONFIG_DIR / "known_servers.json"
ALIASES_FILE = CONFIG_DIR / "aliases.json"

# ----------------------------
# ENSURE DIRECTORIES EXIST
# ----------------------------
def ensure_dir(path: Path):
        path.mkdir(parents=True, exist_ok=True)

def init():
    for d in [
        CONFIG_DIR,
        CACHE_DIR,
        STATE_DIR,
        LOGS_DIR,
        DOWNLOAD_DIR,
        DATA_DIR,
        PLUGINS_DIR,
        PLUGIN_DATA_DIR,
        IN_PROGRESS_DIR,
    ]:
        ensure_dir(d)


init()