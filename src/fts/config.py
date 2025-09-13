import os

# Basic
MAGIC = b'FTS1'
VERSION = 1.1
DEFAULT_FILE_PORT = 5064
DEFAULT_CHAT_PORT = 6064
DISCOVERY_PORT = 1064

# Send/Receive
BUFFER_SIZE =  (1024 * 1024) * 8 # MB
BATCH_SIZE = 4                   # number of chunks per batch
FLUSH_SIZE =  (1024 * 1024) * 16 # MB
MAX_SEND_RETRIES = 5
PROGRESS_INTERVAL = .01          # update progress every 0.01s

# Compression
UNCOMPRESSIBLE_EXTS = {".zip", ".gz", ".bz2", ".xz", ".rar", ".7z", ".jpg", ".jpeg", ".png", ".mp4", ".mp3", ".iso"}

# External dirs
APP_DIR = os.path.expanduser("~/.fts")
os.makedirs(APP_DIR, exist_ok=True)
CERT_FILE = os.path.join(APP_DIR, "cert.pem")
KEY_FILE = os.path.join(APP_DIR, "key.pem")
FINGERPRINT_FILE = os.path.join(APP_DIR, "known_servers.json")
ALIASES_FILE = os.path.join(APP_DIR, "aliases.json")
PID_FILE = os.path.join(APP_DIR, "fts_server.pid")
LIBRARY_FILE = os.path.join(APP_DIR, "library.json")
DEFAULTS_FILE = os.path.join(APP_DIR, "defaults.json")