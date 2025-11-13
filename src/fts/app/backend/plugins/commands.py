import textwrap
import json
import os

from fts.app.backend.plugins.installer import fetch_manifest, list_available_plugins, install_plugin
from fts.app.config import PLUGIN_DIR
from fts import __version__

def cmd_plugins(args, logger):
    try:
        github_version = fetch_manifest()["metadata"][0]["version"]
        current_version = __version__()
        if current_version != github_version:
            logger.warning(f"FTS out of date! New plugins may not be compatible.\n Installed version: {current_version} \n Remote version: {github_version}")
    except Exception:
        logger.warning("Unable to verify FTS version")
    match args.subcommand:
        case "show":
            if not args.plugin:
                list_plugins()
            else:
                show_plugin_details(args.plugin, logger)
        case "install":
            install_plugin(args.plugin, logger)
        case "upgrade":
            if args.force:
                reinstall_plugins(get_installed_plugins(), logger)
                return

            logger.info("Finding outdated plugins")
            outdated = get_outdated_plugins(logger)

            if outdated:
                logger.info("Updating outdated plugins")
                reinstall_plugins(outdated, logger)
            else:
                logger.info("All plugins up-to-date")
        case _:
            logger.error(f"Unknown subcommand : {args.subcommand}")


# ANSI color codes
RESET = "\033[0m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
MAGENTA = "\033[35m"
GRAY = "\033[90m"

def list_plugins():
    """Fetch and pretty-print available FTS plugins with colors indicating install status."""
    plugins = list_available_plugins()
    if not plugins:
        print(f"{RED}No plugins available.{RESET}")
        return

    print(f"\n{CYAN}=== Available FTS Plugins ==={RESET}\n")
    for plugin in plugins:
        desc = textwrap.fill(plugin["description"], width=80)
        authors = ", ".join(plugin["authors"])
        config_file = os.path.join(PLUGIN_DIR, plugin.get("config", ""))

        # Check installation status
        if os.path.exists(config_file):
            status_color = GREEN
            status_text = "Installed"
        else:
            status_color = RED
            status_text = "Not installed"

        print(f"{CYAN}{plugin['name']}{RESET} ({YELLOW}v{plugin['version']}{RESET}) - {status_color}{status_text}{RESET}")
        print(f"  Author(s): {MAGENTA}{authors}{RESET}")
        print(f"  Description: {desc}")
        print("-" * 80)


def show_plugin_details(plugin_name, logger):
    """Display detailed info about a specific installed plugin with colors."""
    config_path = None
    details = None

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

    # Fetch remote version
    try:
        manifest = fetch_manifest()
        remote_plugin = next((p for p in manifest.get("plugins", []) if p["name"].lower() == plugin_name.lower()), None)
        remote_version = remote_plugin.get("version") if remote_plugin else "Unknown"
    except Exception as e:
        remote_version = "Unknown"
        logger.warning(f"Could not fetch remote version: {e}")

    local_version = details.get("version", "Unknown")
    if remote_version == "Unknown":
        status_text = f"{GRAY}Installed{RESET}"
    elif local_version == remote_version:
        status_text = f"{GREEN}Up-to-date{RESET}"
    else:
        status_text = f"{RED}Outdated (Remote: {remote_version}){RESET}"

    # Print plugin info
    print(f"\n{CYAN}=== Plugin Details: {plugin_name} ==={RESET}\n")
    print(f"Title: {CYAN}{details.get('title', plugin_name)}{RESET}")
    print(f"Installed Version: {YELLOW}{local_version}{RESET}")
    print(f"Remote Version: {YELLOW}{remote_version}{RESET}")
    print(f"Status: {status_text}")
    print(f"Author(s): {MAGENTA}{details.get('authors', 'Unknown')}{RESET}")
    print(f"Description:\n{textwrap.fill(details.get('description', 'No description.'), width=80)}")
    print(f"Path: {PLUGIN_DIR}")
    print("-" * 80)


def get_outdated_plugins(logger=None):
    """Return list of installed plugin info that are outdated (dicts with name, local and remote version)."""
    outdated = []

    # Load remote manifest
    try:
        manifest = fetch_manifest()
        remote_plugins = {p['name'].lower(): p for p in manifest.get("plugins", []) if isinstance(p, dict) and "name" in p}
    except Exception as e:
        if logger: logger.error(f"Failed to fetch manifest: {e}")
        return outdated

    # Scan installed plugins (all .json files in PLUGIN_DIR)
    installed_files = [f for f in os.listdir(PLUGIN_DIR) if f.lower().endswith(".json")]
    for f in installed_files:
        plugin_name = os.path.splitext(f)[0]  # preserve casing from file
        config_path = os.path.join(PLUGIN_DIR, f)

        try:
            with open(config_path, "r", encoding="utf-8") as cf:
                local_data = json.load(cf)
                if not isinstance(local_data, dict):
                    continue
        except Exception:
            if logger: logger.warning(f"Skipping unreadable JSON: {f}")
            continue

        local_version = local_data.get("version", "0.0.0")
        remote_info = remote_plugins.get(plugin_name.lower())
        if not remote_info:
            if logger: logger.info(f"No remote info found for '{plugin_name}', skipping.")
            continue

        remote_version = remote_info.get("version", "0.0.0")
        if local_version != remote_version:
            outdated.append({
                "name": plugin_name,
                "local_version": local_version,
                "remote_version": remote_version,
                "remote_info": remote_info
            })

    return outdated


def reinstall_plugins(plugins, logger=None):
    """Reinstall or update the given list of plugins."""
    for plugin in plugins:
        name = plugin.get("name", "Unknown")
        if name == "Unknown":
            continue
        print("-" * 80)
        try:
            if logger: logger.info(f"Updating plugin '{name}'...")
            install_plugin(name, logger)
        except Exception as e:
            if logger: logger.error(f"Failed to update plugin '{name}': {e}")


def get_installed_plugins(logger=None):
    """Return a list of installed plugins as dicts with name and version."""
    installed = []

    if not os.path.isdir(PLUGIN_DIR):
        if logger: logger.warning(f"Plugin directory '{PLUGIN_DIR}' does not exist.")
        return installed

    for f in os.listdir(PLUGIN_DIR):
        if not f.lower().endswith(".json"):
            continue

        config_path = os.path.join(PLUGIN_DIR, f)
        try:
            with open(config_path, "r", encoding="utf-8") as cf:
                data = json.load(cf)
                if isinstance(data, dict) and "name" in data and "version" in data:
                    installed.append({
                        "name": data["name"],
                        "version": data["version"],
                        "path": config_path
                    })
        except Exception:
            if logger: logger.warning(f"Skipping invalid or unreadable plugin JSON: {f}")
            continue

    return installed
