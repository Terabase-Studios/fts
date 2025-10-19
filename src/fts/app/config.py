import os

from fts.config import APP_DIR as app_dir

DISCOVERY_PORT = 6064
CHAT_PORT = 7064

SAVE_DIR = "Downloads"

APP_DIR = app_dir+'/app'
os.makedirs(APP_DIR, exist_ok=True)

SEEN_IPS_FILE = os.path.join(APP_DIR, "seen_ips.json")
CONTACTS_FILE = os.path.join(APP_DIR, "contacts.json")
LOG_FILE      = os.path.join(APP_DIR, "log.txt")


LOGS = [LOG_FILE]