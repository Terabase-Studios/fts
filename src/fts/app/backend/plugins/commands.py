import textwrap
import json
import os

from fts.app.backend.plugins.installer import fetch_manifest, list_available_plugins
from fts.app.config import PLUGIN_DIR
from fts import __version__

def cmd_plugins(args, logger):
    try:
        github_version = fetch_manifest()["metadata"][0]["version"]
        current_version = __version__()
        if current_version != github_version:
            logger.warning(f"FTS out of date! New plugins may not be compatible.\n Installed version: {current_version} \n Github version: {github_version}")
    except Exception:
        logger.warning("Unable to verify FTS version")
    match args.subcommand:
        case "show":
            if not args.plugin:
                list_plugins()
            else:
                show_plugin_details(args.plugin, logger)
        case _:
            logger.error(f"Unknown subcommand : {args.subcommand}")

def list_plugins():
    """Fetch and pretty-print available FTS plugins."""
    plugins = list_available_plugins()
    if not plugins:
        print("No plugins available.")
        return

    print("\n=== Available FTS Plugins ===\n")
    for plugin in plugins:
        desc = textwrap.fill(plugin["description"], width=80)
        authors = ", ".join(plugin["authors"])
        print(f"{plugin['name']} (v{plugin['version']})")
        print(f"  Author(s): {authors}")
        print(f"  Description: {desc}")
        print("-" * 80)

def show_plugin_details(plugin_name, logger):
    """Display detailed information about a specific installed plugin and compare with remote version."""
    config_path = None
    details = None

    # Look for the JSON config in the root of PLUGIN_DIR
    for f in os.listdir(PLUGIN_DIR):
        if f.lower() == plugin_name.lower() + ".json":
            config_path = os.path.join(PLUGIN_DIR, f)
            break

    if not config_path or not os.path.exists(config_path):
        logger.error(f"Plugin '{plugin_name}' not found or missing config JSON in {PLUGIN_DIR}")
        return

    # Load local plugin JSON
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            details = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read plugin config: {e}")
        return

    # Fetch remote manifest and get remote version
    try:
        manifest = fetch_manifest()
        remote_plugin = next((p for p in manifest.get("plugins", []) if p["name"].lower() == plugin_name.lower()), None)
        remote_version = remote_plugin.get("version") if remote_plugin else "Unknown"
    except Exception as e:
        remote_version = "Unknown"
        logger.warning(f"Could not fetch remote version: {e}")

    # Determine status
    local_version = details.get("version", "Unknown")
    if remote_version == "Unknown":
        status = "Installed"
    elif local_version == remote_version:
        status = "Up-to-date"
    else:
        status = f"⚠️ Outdated (Remote: {remote_version})"

    # Print plugin info
    print(f"\n=== Plugin Details: {plugin_name} ===\n")
    print(f"Title: {details.get('title', plugin_name)}")
    print(f"Installed Version: {local_version}")
    print(f"Remote Version: {remote_version}")
    print(f"Status: {status}")
    print(f"Author(s): {details.get('authors', 'Unknown')}")
    print(f"Description:\n{textwrap.fill(details.get('description', 'No description.'), width=80)}")
    print(f"Path: {PLUGIN_DIR}")
    print("-" * 80)
