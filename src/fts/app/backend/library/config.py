import os
from fts.app.config import APP_DIR, LIBRARY_PORT, LIBRARY_IGNORE_HIDDEN_FOLDERS

LIBRARY_PORT = LIBRARY_PORT
IGNORE_HIDDEN_FOLDERS = LIBRARY_IGNORE_HIDDEN_FOLDERS

LIBRARY_CACHE_DIR = os.path.join(APP_DIR, "library")
os.makedirs(LIBRARY_CACHE_DIR, exist_ok=True)

LIBRARY_CACHE_FILE = os.path.join(LIBRARY_CACHE_DIR, "library.json")
LIBRARY_LOG_FILE = os.path.join(LIBRARY_CACHE_DIR, "library_log.json")

LIBRARY_PATH = os.path.expanduser("~/FTS_tool_library")
os.makedirs(LIBRARY_PATH, exist_ok=True)