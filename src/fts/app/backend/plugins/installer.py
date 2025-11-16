import os
import json
import urllib.request
from fts.app.config import PLUGIN_DIR
from fts.app.backend.plugins.config import GITHUB_PLUGIN_DIR
from fts.app.backend.plugins.config import HASHES_JSON, HASHES_SIG, SECURE_PLUGIN_DIR


def download_hashes(logger=None):
    os.makedirs(PLUGIN_DIR, exist_ok=True)

    files_to_download = [HASHES_JSON, HASHES_SIG]

    for filename in files_to_download:
        remote = GITHUB_PLUGIN_DIR + os.path.basename(filename)
        local = os.path.join(SECURE_PLUGIN_DIR, filename)
        try:
            if logger: logger.info(f"Downloading {filename}...")
            urllib.request.urlretrieve(remote, local)
            if logger: logger.info(f"Downloaded {filename}")
        except Exception as e:
            if logger: logger.error(f"Failed to download {filename}: {e}")
            return False

    if logger: logger.info("All hashes files downloaded successfully.")
    return True


def fetch_manifest():
    url = GITHUB_PLUGIN_DIR + "manifest.json"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode())


def install_plugin(name, logger=None):
    try:
        download_hashes()
    except:
        pass
    if logger: logger.info(f"Fetching manifest")
    manifest = fetch_manifest()
    entry = next((p for p in manifest["plugins"] if p["name"].lower() == name.lower()), None)
    if not entry:
        if logger: logger.error(f"Plugin '{name}' not found in manifest.")
        return False

    os.makedirs(PLUGIN_DIR, exist_ok=True)

    if logger: logger.info(f"Downloading files")
    for key in ("entry", "config"):
        remote = GITHUB_PLUGIN_DIR + entry["repo_path"] + entry[key]
        local = os.path.join(PLUGIN_DIR, entry[key])
        urllib.request.urlretrieve(remote, local)
        if logger: logger.info(f"Downloaded {entry[key]}")

    if logger: logger.info(f"Installed {entry['name']}")

    return True


def list_available_plugins():
    """Return manifest plugin info as a list of dicts."""
    manifest = fetch_manifest()
    plugins = []
    for p in manifest.get("plugins", []):
        plugins.append({
            "name": p.get("name", "Unknown"),
            "version": p.get("version", "Unknown"),
            "description": p.get("description", "No description."),
            "authors": p.get("authors", ["Unknown"]),
            "config": p.get("config", "None"),
        })
    return plugins
