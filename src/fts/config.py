"""
FTS configuration values.

Grouped into categories:
- General: magic/version and small global flags
- Networking: default ports and discovery
- Transfer: buffer sizes, batching, retries and progress
- Compression: file types that should *not* be compressed
- Paths: application-specific files (certs, state, etc.)
- DDoS protection: server-side throttling and bans

This module will auto-create a config.ini at APP_DIR/config.ini (if missing)
and then load/override values from it automatically on import.
"""

import configparser
import os
import warnings
from pathlib import Path

# ======================================================
# Default Configuration
# ======================================================
CONFIG_VERSION = 1
current_config_version = int(CONFIG_VERSION)

# -------------------------
# General
# -------------------------
EXPERIMENTAL_FEATURES_ENABLED = False

# -------------------------
# Protocol
# -------------------------
MAGIC = b"FTS1"
VERSION = 2.0

# -------------------------
# Networking
# -------------------------
DEFAULT_FILE_PORT = 5064

# -------------------------
# Transfer / I/O
# -------------------------
BUFFER_SIZE = (1024 * 1024) * 8
BATCH_SIZE = 4
FLUSH_SIZE = (1024 * 1024) * 16
MAX_SEND_RETRIES = 5
PROGRESS_INTERVAL = 0
MID_DOWNLOAD_EXT = ".ftsdownload"

# -------------------------
# Compression
# -------------------------
UNCOMPRESSIBLE_EXTS = {
    # Archives / compressed formats
    ".zip", ".rar", ".7z", ".tar", ".tgz", ".tbz2", ".txz", ".gz", ".bz2", ".xz",
    ".lz", ".lzma", ".lz4", ".zst", ".z", ".arj", ".cab", ".ace", ".arc", ".pak",
    ".unitypackage", ".jar", ".apk", ".war", ".ear", ".deb", ".rpm", ".xar", ".cpio",
    ".squashfs", ".vpk", ".pkg", ".dmg", ".hfs", ".hfsplus", ".vhd", ".vhdx", ".vmdk",
    ".vdi", ".qcow2", ".img", ".iso", ".udf", ".7zp", ".tar.gz", ".tar.bz2", ".tar.xz",

    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif",
    ".ico", ".svg", ".raw", ".cr2", ".nef", ".orf", ".arw", ".dng", ".raf", ".rw2",
    ".psd", ".ai", ".xcf", ".cdr", ".indd", ".sketch", ".dwg", ".dxf", ".3ds", ".blend",
    ".max", ".obj", ".fbx", ".stl", ".dae", ".ply", ".mtl", ".eps",

    # Video
    ".mp4", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg",
    ".3gp", ".ogv", ".mts", ".m2ts", ".vob", ".rm", ".rmvb", ".asf", ".ts", ".f4v",
    ".mxf", ".divx", ".xvid", ".qt", ".yuv",

    # Audio
    ".mp3", ".aac", ".flac", ".wav", ".wma", ".m4a", ".ogg", ".opus", ".alac", ".aiff",
    ".au", ".ra", ".amr", ".mka", ".caf", ".mid", ".midi", ".snd", ".pcm",

    # Executables / system
    ".exe", ".msi", ".dll", ".sys", ".bat", ".com", ".elf", ".app", ".bin", ".sh",
    ".pyc", ".pyd", ".so", ".class", ".out", ".ipa", ".command", ".vbs", ".ps1",

    # Documents / Office
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
    ".rtf", ".pages", ".key", ".numbers", ".xmind", ".one", ".vsdx", ".epub", ".mobi",

    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot", ".fon", ".pfb", ".pfm", ".fnt", ".sfd",

    # Game / engine packages
    ".pak", ".unitypackage", ".umap", ".uasset", ".bsp", ".wad", ".vpk", ".gma",
    ".pak01", ".pak02", ".pak03", ".pak04",

    # Database / system files
    ".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".ndb", ".nsf", ".ldb", ".log", ".lock",

    # Miscellaneous compressed / uncommon
    ".zoo", ".shar", ".sit", ".sitx", ".apkx", ".pxz", ".s7z", ".sbx", ".pakx",

    # Virtual machine / disk images
    ".vmdk", ".vdi", ".vhd", ".vhdx", ".qcow2", ".img", ".iso", ".bin", ".dmg", ".raw",

    # Backup / snapshot formats
    ".bak", ".bkf", ".svf", ".tar.old", ".tar.backup", ".snapshot", ".delta",

    # Other media or already compressed
    ".mp4a", ".webm", ".ogm", ".flv", ".mod", ".vob", ".m2v", ".m1v", ".m2p", ".m2t",
    ".m2ts", ".mkv", ".mts", ".m2t", ".mxf", ".divx", ".xvid", ".qt", ".yuv",

    # Code archives / packages
    ".gem", ".whl", ".egg", ".nupkg", ".rpm", ".deb", ".tar.gz", ".tar.bz2",

    # System / firmware
    ".rom", ".bin", ".img", ".hex", ".uf2", ".dfu", ".fw", ".dfm", ".mbn", ".cap"
}

# -------------------------
# Paths
# -------------------------
APP_DIR = os.path.expanduser("~/.fts")
os.makedirs(APP_DIR, exist_ok=True)

CERT_FILE = os.path.join(APP_DIR, "cert.pem")
KEY_FILE = os.path.join(APP_DIR, "key.pem")
FINGERPRINT_FILE = os.path.join(APP_DIR, "known_servers.json")
ALIASES_FILE = os.path.join(APP_DIR, "aliases.json")
RECEIVING_PID = os.path.join(APP_DIR, "fts_receiver.pid")

# -------------------------
# DDoS Protection
# -------------------------
DOSP_ENABLED = False
MAX_REQS_PER_MIN = 30
MAX_BYTES_PER_MIN = pow(1024, 3) * 10
BAN_SECONDS = 120
REQUEST_WINDOW = 600.0

# -------------------------
# Config File
# -------------------------
CONFIG_FILE = os.path.join(APP_DIR, "config.ini")

# ======================================================
# Helper Functions
# ======================================================

def _serialize_set(s: set) -> str:
    return ", ".join(sorted(s))

def _deserialize_set(s: str) -> set:
    if not s:
        return set()
    return {p.strip() for p in s.split(",") if p.strip()}

def _write_default_config(path: str):
    """Generate a default config.ini if none exists."""
    cp = configparser.ConfigParser()

    cp["general"] = {
        "config_version": str(CONFIG_VERSION),
        "experimental_features_enabled": str(EXPERIMENTAL_FEATURES_ENABLED),
    }

    cp["networking"] = {
        "default_file_port": str(DEFAULT_FILE_PORT),
    }

    cp["transfer"] = {
        "buffer_size": str(BUFFER_SIZE),
        "batch_size": str(BATCH_SIZE),
        "flush_size": str(FLUSH_SIZE),
        "max_send_retries": str(MAX_SEND_RETRIES),
        "progress_interval": str(PROGRESS_INTERVAL),
    }

    cp["paths"] = {
        "app_dir": APP_DIR,
    }

    cp["ddos"] = {
        "dosp_enabled": str(DOSP_ENABLED),
        "max_reqs_per_min": str(MAX_REQS_PER_MIN),
        "max_bytes_per_min": str(MAX_BYTES_PER_MIN),
        "ban_seconds": str(BAN_SECONDS),
        "request_window": str(REQUEST_WINDOW),
    }

    cp["compression"] = {
        "uncompressible_exts": _serialize_set(UNCOMPRESSIBLE_EXTS),
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)
        #print(f"[FTS Config] Created default config.ini at {path}")
    except Exception as e:
        warnings.warn(f"Failed to write default config.ini: {e}")

def _coerce_value(key: str, value: str):
    """Convert INI strings to appropriate Python types."""
    if value is None:
        return None
    k = key.lower()

    # Boolean
    if k.endswith("_enabled") or k.startswith("enable_"):
        return value.strip().lower() in ("1", "true", "yes", "on", "y")

    # Integers
    if k.endswith("_port") or k.endswith("_size") or k.endswith("_retries") or k.endswith("_min") or k.endswith("_seconds") or k == "config_version":
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except Exception:
                warnings.warn(f"Failed to parse int for {key}='{value}'")
                return value

    # Floats
    if k.endswith("_interval") or k.endswith("_window") or k == "version":
        try:
            return float(value)
        except Exception:
            return value

    # Sets
    if "exts" in k:
        return _deserialize_set(value)

    # Bytes
    if k == "magic":
        return value.encode("utf-8")

    return value

def _load_config_from_ini(path: str):
    """Load and apply overrides from config.ini."""
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")

    for section in cp.sections():
        for key, raw_val in cp.items(section):
            py_val = _coerce_value(key, raw_val)
            globals()[key.upper()] = py_val


def load_or_create_config(path: str = CONFIG_FILE):
    """Ensure config.ini exists and load it."""
    global CONFIG_FILE, CERT_FILE, KEY_FILE, FINGERPRINT_FILE, ALIASES_FILE, RECEIVING_PID
    p = Path(path)
    if not p.exists():
        _write_default_config(path)
    _load_config_from_ini(path)
    CONFIG_FILE = os.path.join(APP_DIR, "config.ini")
    CERT_FILE = os.path.join(APP_DIR, "cert.pem")
    KEY_FILE = os.path.join(APP_DIR, "key.pem")
    FINGERPRINT_FILE = os.path.join(APP_DIR, "known_servers.json")
    ALIASES_FILE = os.path.join(APP_DIR, "aliases.json")
    RECEIVING_PID = os.path.join(APP_DIR, "fts_receiver.pid")

# ======================================================
# Auto-run on import
# ======================================================
broken_config = False
try:
    last_config = CONFIG_FILE
    load_or_create_config(CONFIG_FILE)
    warned = False
    while last_config != CONFIG_FILE:
        if not warned:
            print('WARNING: Changing APP_DIR is not recommended, as it may cause unpredictable behavior!')
        load_or_create_config(CONFIG_FILE)
        last_config = CONFIG_FILE
except Exception as e:
    print(f"ERROR: failed to load {CONFIG_FILE}: {e}")
    broken_config = True

def backup_config(path: str):
    if not os.path.exists(path):
        return

    base = path + ".backup"
    i = 0

    while True:
        suffix = f".{i}" if i else ""
        candidate = base + suffix
        if not os.path.exists(candidate + ".txt"):
            os.rename(path, candidate + ".txt")
            break
        i += 1

def resave_config():
    """Save config to config.ini and move existing config.ini to back up."""
    global CONFIG_VERSION
    backup_config(CONFIG_FILE)
    CONFIG_VERSION = current_config_version
    _write_default_config(CONFIG_FILE)

if broken_config:
    print("INFO: Recreating config.ini with default settings, a backup will be saved in the same directory.")
    resave_config()
elif CONFIG_VERSION != current_config_version:
    print("INFO: Migrating config.ini to a new config version, a backup will be saved in the same directory.")
    resave_config()