"""
FTS configuration values.

Grouped into categories:
- General: magic/version and small global flags
- Networking: default ports and discovery
- Transfer: buffer sizes, batching, retries and progress
- Compression: file types that should *not* be compressed
- Paths: application-specific files (certs, state, etc.)
- DDoS protection: server-side throttling and bans

This module will create a config.ini at APP_DIR/config.ini (if missing)
and then load/override values from it on import.
"""

import configparser
import os
import warnings
from pathlib import Path

# -------------------------
# General
# -------------------------
MAGIC = b"FTS1"         # protocol magic bytes used at connection start
VERSION = 2.0           # fts protocol version
# Toggle features can live here in future (e.g. DEBUG, FEATURE_FLAGS)

# -------------------------
# Networking (default ports)
# -------------------------
DEFAULT_FILE_PORT = 5064     # TCP port used for file transfers
DEFAULT_CHAT_PORT = 6064     # TCP port used for chat service
DISCOVERY_PORT = 1064        # UDP/TCP port used for local service discovery

# -------------------------
# Transfer / I/O tuning
# -------------------------
# Sizes are expressed in bytes.
# Adjust to balance memory use vs throughput on typical hosts.
BUFFER_SIZE = (1024 * 1024) * 8    # read/write buffer size in bytes (8 MiB)
BATCH_SIZE = 4                     # number of chunks sent together in a batch
FLUSH_SIZE = (1024 * 1024) * 16    # when to flush/send an aggregated buffer (16 MiB)
MAX_SEND_RETRIES = 5               # number of times to retry a failed send operation
PROGRESS_INTERVAL = 0              # progress update interval in seconds (0 = every update)

# -------------------------
# Compression
# -------------------------
# File extensions that are normally already compressed and shouldn't be re-compressed.
UNCOMPRESSIBLE_EXTS = {
    ".zip", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".jpg", ".jpeg", ".png", ".mp4", ".mp3", ".iso",
}

# -------------------------
# Paths / External files
# -------------------------
# Directory for FTS to store persistent state (certs, aliases, caches, pids, etc.).
APP_DIR = os.path.expanduser("~/.fts")
os.makedirs(APP_DIR, exist_ok=True)

# TLS / TOFU files
CERT_FILE = os.path.join(APP_DIR, "cert.pem")               # local public cert (PEM)
KEY_FILE = os.path.join(APP_DIR, "key.pem")                 # local private key (PEM)
FINGERPRINT_FILE = os.path.join(APP_DIR, "known_servers.json")  # known server fingerprints (TOFU store)

# Local application state
ALIASES_FILE = os.path.join(APP_DIR, "aliases.json")       # saved user aliases (ip/dir)

# PID files for detached/background processes
RECEIVING_PID = os.path.join(APP_DIR, "fts_receiver.pid")  # pid file for receiver (open) process
# -------------------------
# Server DDoS protection (per-IP limits)
# -------------------------
# Toggle enforcement of simple in-memory protections.
DOSP_ENABLED = True                    # if False, protector code can be bypassed

# Limits and windows (tweak according to deployment & capacity)
MAX_REQS_PER_MIN = 30                  # max requests per IP per minute
MAX_BYTES_PER_MIN = pow(1024, 3) * 10      # max bytes per IP per minute (10 GiB)
BAN_SECONDS = 120                      # temporary ban length in seconds when limits exceeded
REQUEST_WINDOW = 600.0                  # sliding window length in seconds used for counting

# -------------------------
# Notes
# -------------------------
# - All numeric sizes are bytes/seconds unless otherwise noted.
# - If you run multiple worker processes, in-memory DDoS stats will not be shared.

# -------------------------
# Config file handling (config.ini)
# -------------------------
CONFIG_FILE = os.path.join(APP_DIR, "config.ini")


def _serialize_set(s: set) -> str:
    """Serialize a set of strings to a comma-separated string for the INI."""
    return ", ".join(sorted(s))


def _deserialize_set(s: str) -> set:
    """Turn a comma-separated INI value back into a set of normalized strings."""
    if s is None:
        return set()
    parts = [p.strip() for p in s.split(",") if p.strip()]
    return set(parts)


def _write_default_config(path: str):
    """
    Write a default config.ini to `path`. This is called only when the file
    doesn't already exist to give users a place to tweak settings.
    """
    cp = configparser.ConfigParser()

    cp["networking"] = {
        "default_file_port": str(DEFAULT_FILE_PORT),
        "default_chat_port": str(DEFAULT_CHAT_PORT),
        "discovery_port": str(DISCOVERY_PORT),
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

    with open(path, "w", encoding="utf-8") as f:
        cp.write(f)


def _coerce_value(key: str, value: str):
    """
    Coerce a string value from the INI into a Python object using heuristics
    based on key names.
    """
    if value is None:
        return None
    key = key.lower()
    # bool-like
    if key.endswith("_enabled") or key in ("dosp_enabled",):
        v = value.strip().lower()
        return v in ("1", "true", "yes", "on", "y")
    # ints
    if key.endswith("_port") or key.endswith("_size") or key.endswith("_retries") or key.endswith("_min") or key.endswith("_seconds"):
        try:
            return int(value)
        except ValueError:
            # some values (like BUFFER_SIZE) may be large; if int fails, try float then int
            try:
                return int(float(value))
            except Exception:
                warnings.warn(f"Failed to parse int for {key}='{value}', leaving as string")
                return value
    # floats
    if key.endswith("_interval") or key.endswith("_window") or key in ("version",):
        try:
            return float(value)
        except Exception:
            return value
    # sets / lists
    if key in ("uncompressible_exts", "uncompressible_ext"):
        return _deserialize_set(value)
    # default: return string (but allow bytes for magic)
    if key in ("magic",):
        return value.encode("utf-8")
    return value


def _load_config_from_ini(path: str):
    """
    Load the config.ini, coerce values to appropriate types, and set module-level
    constants accordingly (mutating globals()).
    """
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")

    # mapping from INI section -> how we map keys to module-level names
    section_key_map = {
        "general": {},
        "networking": {},
        "transfer": {},
        "compression": {},
        "paths": {},
        "ddos": {},
    }

    # Iterate through all sections and items, coerce and assign to globals
    for section in cp.sections():
        for key, raw_val in cp.items(section):
            py_val = _coerce_value(key, raw_val)
            # map INI key to uppercase module name if possible
            module_name = key.upper()
            # Special mapping adjustments for names that differ
            # e.g. uncompressible_exts -> UNCOMPRESSIBLE_EXTS etc. (already handled by upper())
            # Accept both snake_case and the exact names already in this module.
            # Only assign if the name exists in globals() or create new global.
            globals()[module_name] = py_val


def load_or_create_config(path: str = CONFIG_FILE):
    """
    Ensure a config file exists at `path`, create it with defaults if not,
    then load it and apply overrides to module-level constants.
    """
    p = Path(path)
    if not p.exists():
        try:
            _write_default_config(path)
        except Exception as e:
            warnings.warn(f"Failed to write default config.ini to '{path}': {e}")
    try:
        _load_config_from_ini(path)
    except Exception as e:
        warnings.warn(f"Failed to load config.ini '{path}': {e}")


# Run at import time so values are available to callers.
#load_or_create_config(CONFIG_FILE)