import os
import json
import urllib.request
from fts.app.config import PLUGIN_DIR

GITHUB_BASE = "https://raw.githubusercontent.com/Terabase-Studios/fts/refs/heads/main/plugins/"


def fetch_manifest():
    url = GITHUB_BASE + "manifest.json"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode())


def install_plugin_from_manifest(name, logger=None):
    manifest = fetch_manifest()
    entry = next((p for p in manifest["plugins"] if p["name"] == name), None)
    if not entry:
        if logger: logger.error(f"Plugin '{name}' not found in manifest.")
        return False

    os.makedirs(PLUGIN_DIR, exist_ok=True)

    for key in ("entry", "config"):
        remote = GITHUB_BASE + entry["repo_path"] + entry[key]
        local = os.path.join(PLUGIN_DIR, entry[key])
        urllib.request.urlretrieve(remote, local)
        if logger: logger.info(f"Downloaded {entry[key]} for {name}")

    return True


def list_available_plugins():
    manifest = fetch_manifest()
    return [(p["name"], p["version"], p["description"], [["author"]]) for p in manifest["plugins"]]

print(install_plugin_from_manifest('ai_chat'))