from fts.cache import CONFIG_FILE
from fts.app.cache import CONFIG_FILE as APP_CONFIG_FILE

LEGACY_MAP = {
    # config
    "config.ini": CONFIG_FILE,
    "app/config.ini": CONFIG_FILE,

    # logs
    "log.txt": LOG_FILE,
    "app/log.txt": LOG_FILE,
    "debug.txt": DEBUG_FILE,
    "app/debug.txt": DEBUG_FILE,

    # state
    "seen_ips.json": SEEN_IPS_FILE,
    "app/seen_ips.json": SEEN_IPS_FILE,
    "macs.json": MAC_FILE,
    "muted.json": MUTED_FILE,
    "app/macs.json": MAC_FILE,
    "app/muted.json": MUTED_FILE,

    # plugins
    "app/plugins": PLUGINS_DIR,

    # secure
    "app/plugins_secure": SECURE_PLUGIN_DIR,

    # library cache
    "app/library/library.json": LIBRARY_CACHE_FILE,

    # transfers
    "in_progress": IN_PROGRESS_DIR,

    # keys / cert
    "cert.pem": CERT_FILE,
    "key.pem": KEY_FILE,
}