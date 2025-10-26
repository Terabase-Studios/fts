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

# -------------------------
# General
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
    ".zip", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".jpg", ".jpeg", ".png", ".mp4", ".mp3", ".iso",
    ".exe", ".7zp", ".tar"
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

    cp["compression"] = {
        "uncompressible_exts": _serialize_set(UNCOMPRESSIBLE_EXTS),
    }

    cp["paths"] = {
        "app_dir": APP_DIR,
        "cert_file": CERT_FILE,
        "key_file": KEY_FILE,
        "fingerprint_file": FINGERPRINT_FILE,
        "aliases_file": ALIASES_FILE,
        "receiving_pid": RECEIVING_PID,
    }

    cp["ddos"] = {
        "dosp_enabled": str(DOSP_ENABLED),
        "max_reqs_per_min": str(MAX_REQS_PER_MIN),
        "max_bytes_per_min": str(MAX_BYTES_PER_MIN),
        "ban_seconds": str(BAN_SECONDS),
        "request_window": str(REQUEST_WINDOW),
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
    if k.endswith("_port") or k.endswith("_size") or k.endswith("_retries") or k.endswith("_min") or k.endswith("_seconds"):
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
    p = Path(path)
    if not p.exists():
        _write_default_config(path)
    _load_config_from_ini(path)

# ======================================================
# Auto-run on import
# ======================================================
load_or_create_config(CONFIG_FILE)
