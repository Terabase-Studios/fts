import os

DEFAULT_PORT = 5064
BUFFER_SIZE = 1024 * 128
MAX_SEND_RETRIES = 5

MAGIC = b'FTS1'
VERSION = 1.1

APP_DIR = os.path.expanduser("~/.fts")
os.makedirs(APP_DIR, exist_ok=True)
CERT_FILE = os.path.join(APP_DIR, "cert.pem")
KEY_FILE = os.path.join(APP_DIR, "key.pem")
FINGERPRINT_FILE = os.path.join(APP_DIR, "known_servers.json")
ALIASES_FILE = os.path.join(APP_DIR, "aliases.json")