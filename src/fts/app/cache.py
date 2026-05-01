from pathlib import Path
from platformdirs import PlatformDirs

from fts.cache import ensure_dir

dirs = PlatformDirs("Fts-Tool", "Terabase")

CONFIG_DIR = Path(dirs.user_config_dir)
CACHE_DIR = Path(dirs.user_cache_dir)
STATE_DIR = Path(dirs.user_state_dir)
LOGS_DIR = Path(dirs.user_log_dir)
DOWNLOAD_DIR = Path(dirs.user_downloads_dir)
DATA_DIR = Path(dirs.user_data_dir)

# ----------------------------
# CONFIG (user settings / identity)
# ----------------------------
CONFIG_FILE = CONFIG_DIR / "app_config.ini"
CONTACTS_FILE = CONFIG_DIR / "contacts.json"
MUTED_FILE = CONFIG_DIR / "muted.json"
MAC_FILE = CONFIG_DIR / "macs.json"

# ----------------------------
# STATE (runtime + sessions)
# ----------------------------
SEEN_IPS_FILE = STATE_DIR / "seen_ips.json"
CHAT_FILE = STATE_DIR / "chat.json"
LOCK_FILE = STATE_DIR / "lock.lock"

# ----------------------------
# LOGS / DEBUG
# ----------------------------
LOG_FILE = LOGS_DIR / "log.txt"
DEBUG_FILE = LOGS_DIR / "debug.txt"

# ----------------------------
# PLUGINS
# ----------------------------
PLUGIN_DIR = CONFIG_DIR / "plugins"

SECURE_PLUGIN_DIR = CONFIG_DIR / "plugins_secure"
HASHES_JSON = SECURE_PLUGIN_DIR / "hashes.json"
HASHES_SIG = SECURE_PLUGIN_DIR / "hashes.sig"

# ----------------------------
# CACHE (rebuildable only)
# ----------------------------
LIBRARY_CACHE_DIR = CACHE_DIR / "library"
LIBRARY_CACHE_FILE = LIBRARY_CACHE_DIR / "library.json"
LIBRARY_LOG_FILE = LIBRARY_CACHE_DIR / "library_log.json"

# ----------------------------
# EXTERNAL / USER LIBRARY PATH
# ----------------------------
LIBRARY_PATH = Path.home() / "FTS_tool_library"

# ----------------------------
# ENSURE DIRECTORIES EXIST
# ----------------------------
def init():
    for d in [
        CONFIG_DIR,
        CACHE_DIR,
        STATE_DIR,
        LOGS_DIR,
        DOWNLOAD_DIR,
        DATA_DIR,
        PLUGIN_DIR,
        SECURE_PLUGIN_DIR,
        LIBRARY_CACHE_DIR,
    ]:
        ensure_dir(d)

    # ----------------------------
    # ENSURE FILES EXIST
    # ----------------------------
    for file in [LOG_FILE, DEBUG_FILE]:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch(exist_ok=True)

init()