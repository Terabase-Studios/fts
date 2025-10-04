from fts.config import APP_DIR as app_dir
import os

APP_DIR = app_dir+'/app'
os.makedirs(APP_DIR, exist_ok=True)

SEEN_IPS_FILE = os.path.join(APP_DIR, "seen_ips.json")
CONTACTS_FILE = os.path.join(APP_DIR, "contacts.json")


LOGS = ["C:\\Users\\cybor\\Downloads\\log.txt"]