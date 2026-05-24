import json
import os
import urllib.request

from fts.app.backend.plugins.config import API_PLUGIN_DIR, API_PLUGIN_ARGS, API_PLUGIN_HEADERS
from fts.app.cache import PLUGIN_DIR, HASHES_JSON, HASHES_SIG, SECURE_PLUGIN_DIR


def download_hashes(logger=None):
    os.makedirs(PLUGIN_DIR, exist_ok=True)

    files_to_download = [HASHES_JSON, HASHES_SIG]

    for filename in files_to_download:
        remote = API_PLUGIN_DIR + os.path.basename(filename) + API_PLUGIN_ARGS
        local = os.path.join(SECURE_PLUGIN_DIR, filename)

        try:
            if logger: logger.info(f"Downloading {filename}...")

            req = urllib.request.Request(remote, headers=API_PLUGIN_HEADERS)
            with urllib.request.urlopen(req) as r:
                data = r.read()

            with open(local, "wb") as f:
                f.write(data)

            if logger: logger.info(f"Downloaded {filename}")

        except Exception as e:
            if logger: logger.error(f"Failed to download {filename}: {e}")
            return False

    return True


def fetch_manifest():
    url = API_PLUGIN_DIR + "manifest.json" + API_PLUGIN_ARGS
    req = urllib.request.Request(url, headers=API_PLUGIN_HEADERS)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def download_file(url, local_path, headers):
    req = urllib.request.Request(url + API_PLUGIN_ARGS, headers=headers)
    with urllib.request.urlopen(req) as r:
        data = r.read()

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(data)


def install_plugin(name, logger=None):
    try:
        download_hashes(logger)
    except Exception:
        pass

    if logger:
        logger.info("Fetching manifest")

    manifest = fetch_manifest()
    entry = next(
        (p for p in manifest.get("plugins", []) if p["name"].lower() == name.lower()),
        None
    )

    if not entry:
        if logger:
            logger.error(f"Plugin '{name}' not found in manifest.")
        return False

    os.makedirs(PLUGIN_DIR, exist_ok=True)

    if logger:
        logger.info("Downloading files")

    # Download plugin files (FIXED: no urlretrieve)
    for key in ("entry", "config"):
        remote = API_PLUGIN_DIR + entry["repo_path"] + entry[key]
        local = os.path.join(PLUGIN_DIR, entry[key])

        try:
            download_file(remote, local, API_PLUGIN_HEADERS)
            if logger:
                logger.info(f"Downloaded {entry[key]}")
        except Exception as e:
            if logger:
                logger.error(f"Failed to download {entry[key]}: {e}")
            return False

    # Update config with installed version
    config_path = os.path.join(PLUGIN_DIR, entry["config"])

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            local_config = json.load(f)

        if isinstance(local_config, dict):
            local_config["installed_version"] = entry["version"]

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(local_config, f, indent=2)
                f.write("\n")

    except Exception as e:
        if logger:
            logger.warning(
                f"Could not write installed version to {entry['config']}: {e}"
            )

    if logger:
        logger.info(f"Installed {entry['name']}")

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
