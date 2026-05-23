import configparser
import json
import os
import shutil
import textwrap

from fts import __version__
from fts.app.backend.plugins.installer import fetch_manifest, list_available_plugins, install_plugin, download_hashes
from fts.app.cache import PLUGIN_DIR, CONFIG_DIR


def cmd_plugins(args, logger):
    try:
        github_version = fetch_manifest()["metadata"][0]["version"]
        current_version = __version__()
        if current_version != github_version:
            logger.warning(
                f"FTS out of date! New plugins may not be compatible.\n Installed version: {current_version} \n Remote version: {github_version}")
    except Exception:
        logger.warning("Unable to verify FTS version")
    if args.subcommand == "show":
        if not args.plugin:
            try:
                list_plugins()
            except Exception as e:
                logger.error(f"Failed to get plugins: {e}")
        else:
            show_plugin_details(args.plugin, logger)

    elif args.subcommand == "install":
        logger.info("Updating plugin hashes\nAny outdated plugins may not be compatible")
        try:
            success = download_hashes()
        except:
            success = False

        if not success:
            logger.error("Failed to update plugin hashes!\nRun `fts plugins upgrade` to try again")

        all_plugins = [i for i in args.plugin if i.lower() == "all"]
        if all_plugins:
            manifest = fetch_manifest()
            args.plugin = {
                p['name'].lower(): p
                for p in manifest.get("plugins", [])
                if isinstance(p, dict) and "name" in p
            }

        for plugin in args.plugin:
            try:
                install_plugin(plugin, logger)
            except Exception as e:
                logger.error(f"Failed to install plugin {plugin}: {e}")
            print("-" * 80)

    elif args.subcommand == "upgrade":
        if args.force:
            reinstall_plugins(get_installed_plugins(), logger)
            return

        logger.info("Updating plugin hashes")
        try:
            success = download_hashes()
        except:
            success = False

        if not success:
            logger.error("Failed to download plugin hashes")

        logger.info("Finding outdated plugins")
        outdated = get_outdated_plugins(logger)

        if outdated:
            logger.info("Updating outdated plugins")
            reinstall_plugins(outdated, logger)
        else:
            logger.info("All plugins up-to-date")

    elif args.subcommand == "uninstall":
        all_plugins = [i for i in args.plugin if i.lower() == "all"]
        if all_plugins:
            args.plugin = [i["name"] for i in get_installed_plugins(logger=logger)]

        for plugin in args.plugin:
            uninstall_plugin(plugin, all_files=args.all, logger=logger)
            print("-" * 80)

    else:
        logger.error(f"Unknown subcommand : {args.subcommand}")


# ANSI color codes
RESET = "\033[0m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
MAGENTA = "\033[35m"
GRAY = "\033[90m"


def _plugin_name_from_config(config_path):
    return os.path.splitext(os.path.basename(config_path))[0]


def _get_remote_plugins(logger=None):
    try:
        manifest = fetch_manifest()
        return {
            p["name"].lower(): p
            for p in manifest.get("plugins", [])
            if isinstance(p, dict) and "name" in p
        }
    except Exception as e:
        if logger:
            logger.warning(f"Could not fetch remote plugin manifest: {e}")
        return {}


def _read_plugin_config(config_path, logger=None):
    try:
        with open(config_path, "r", encoding="utf-8") as cf:
            data = json.load(cf)
            if isinstance(data, dict):
                return data
    except Exception:
        if logger:
            logger.warning(f"Skipping invalid or unreadable plugin JSON: {os.path.basename(config_path)}")
    return {}


def _plugin_name(local_data, config_path):
    return local_data.get("name") or _plugin_name_from_config(config_path)


def _installed_version(local_data):
    return local_data.get("installed_version") or local_data.get("version")


def _entry_file(local_data, remote_info, config_path):
    return (
        local_data.get("entry")
        or remote_info.get("entry")
        or f"{_plugin_name(local_data, config_path)}.py"
    )


def list_plugins():
    """Fetch and pretty-print available FTS plugins with colors indicating install/update status."""
    plugins = list_available_plugins()
    if not plugins:
        print(f"{RED}No plugins available.{RESET}")
        return

    remote_plugins = _get_remote_plugins()

    print(f"\n{CYAN}=== Available FTS Plugins ==={RESET}\n")

    for plugin in plugins:
        name = plugin["name"]
        desc = textwrap.fill(plugin["description"], width=80)
        authors = ", ".join(plugin["authors"])
        config_file = os.path.join(PLUGIN_DIR, plugin.get("config", ""))

        local_version = None
        if os.path.exists(config_file):
            local_version = _installed_version(_read_plugin_config(config_file))

        remote_version = remote_plugins.get(name.lower(), {}).get("version")

        # Determine status
        if not local_version:
            status_color = RED
            status_text = "Not installed"
        elif not remote_version or local_version == remote_version:
            status_color = GREEN
            status_text = "Up-to-date"
        else:
            status_color = YELLOW
            status_text = f"Outdated → v{remote_version}"

        print(
            f"{CYAN}{name}{RESET} "
            f"({YELLOW}v{plugin['version']}{RESET}) - "
            f"{status_color}{status_text}{RESET}"
        )
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

    remote_plugin = _get_remote_plugins(logger).get(plugin_name.lower(), {})
    remote_version = remote_plugin.get("version", "Unknown")

    local_version = _installed_version(details) or "Unknown"
    if remote_version == "Unknown":
        status_text = f"{GRAY}Installed{RESET}"
    elif local_version == remote_version:
        status_text = f"{GREEN}Up-to-date{RESET}"
    else:
        status_text = f"{RED}Outdated (Remote: {remote_version}){RESET}"

    # Print plugin info
    print(f"\n{CYAN}=== Plugin Details: {plugin_name} ==={RESET}\n")
    print(f"Title: {CYAN}{details.get('title') or remote_plugin.get('title', plugin_name)}{RESET}")
    print(f"Installed Version: {YELLOW}{local_version}{RESET}")
    print(f"Remote Version: {YELLOW}{remote_version}{RESET}")
    print(f"Status: {status_text}")
    authors = details.get("authors") or remote_plugin.get("authors", ["Unknown"])
    if isinstance(authors, list):
        authors = ", ".join(authors)
    print(f"Author(s): {MAGENTA}{authors}{RESET}")
    description = details.get("description") or remote_plugin.get("description", "No description.")
    print(f"Description:\n{textwrap.fill(description, width=80)}")
    print(f"Path: {PLUGIN_DIR}")
    print("-" * 80)


def get_outdated_plugins(logger=None):
    """Return list of installed plugin info that are outdated (dicts with name, local and remote version)."""
    outdated = []

    remote_plugins = _get_remote_plugins(logger)
    if not remote_plugins:
        return outdated

    # Scan installed plugins (all .json files in PLUGIN_DIR)
    installed_files = [f for f in os.listdir(PLUGIN_DIR) if f.lower().endswith(".json")]
    for f in installed_files:
        plugin_name = os.path.splitext(f)[0]  # preserve casing from file
        config_path = os.path.join(PLUGIN_DIR, f)

        local_data = _read_plugin_config(config_path, logger)
        if not local_data:
            continue

        plugin_name = _plugin_name(local_data, config_path)
        local_version = _installed_version(local_data) or "0.0.0"
        remote_info = remote_plugins.get(plugin_name.lower())
        if not remote_info:
            continue

        remote_version = remote_info.get("version", "0.0.0")
        if local_version != remote_version:
            outdated.append({
                "name": remote_info.get("name", plugin_name),
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
                if isinstance(data, dict):
                    name = _plugin_name(data, config_path)
                    version = _installed_version(data)
                    if not version:
                        continue
                    installed.append({
                        "name": name,
                        "version": version,
                        "path": config_path
                    })
        except Exception:
            if logger: logger.warning(f"Skipping invalid or unreadable plugin JSON: {f}")
            continue

    return installed


def uninstall_plugin(plugin_name, all_files=False, logger=None):
    """
    Uninstall a plugin by removing its .py and .json files.
    If all_files=True, also delete any files listed under "addons" in the plugin's JSON.
    """
    config_path = None

    # Find the plugin config
    for f in os.listdir(PLUGIN_DIR):
        if f.lower() == plugin_name.lower() + ".json":
            config_path = os.path.join(PLUGIN_DIR, f)
            break

    if not config_path or not os.path.exists(config_path):
        if logger: logger.error(f"Plugin '{plugin_name}' not found in {PLUGIN_DIR}")
        return

    # Load plugin JSON
    try:
        with open(config_path, "r", encoding="utf-8") as cf:
            data = json.load(cf)
    except Exception as e:
        if logger: logger.error(f"Failed to read config for '{plugin_name}': {e}")
        return

    remote_info = _get_remote_plugins(logger).get(plugin_name.lower(), {})

    # Delete the main .py entry file
    py_file = os.path.join(PLUGIN_DIR, _entry_file(data, remote_info, config_path))
    if os.path.exists(py_file):
        try:
            os.remove(py_file)
            if logger: logger.info(f"Deleted {py_file}")
        except Exception as e:
            if logger: logger.error(f"Failed to delete {py_file}: {e}")

    # Delete the JSON config itself
    try:
        os.remove(config_path)
        if logger: logger.info(f"Deleted {config_path}")
    except Exception as e:
        if logger: logger.error(f"Failed to delete {config_path}: {e}")

    # Optionally delete additional addon files listed in "addons"
    if all_files:
        for addon_file in data.get("addons", []):
            addon_path = os.path.join(PLUGIN_DIR, addon_file)
            if os.path.exists(addon_path):
                try:
                    os.remove(addon_path)
                    if logger: logger.info(f"Deleted addon file {addon_path}")
                except Exception as e:
                    if logger: logger.error(f"Failed to delete addon file {addon_path}: {e}")

    # Remove plugin from CONFIG_PATH [plugins] section
    try:
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_DIR)

        # normalize key names: remove case-insensitive match
        plugin_key = plugin_name.lower()
        if cfg.has_section("plugins") and plugin_key in cfg["plugins"]:
            cfg.remove_option("plugins", plugin_key)
            with open(CONFIG_DIR, "w", encoding="utf-8") as f:
                cfg.write(f)
            if logger: logger.info(f"Removed '{plugin_name}' from config [{CONFIG_DIR}]")
    except Exception as e:
        if logger: logger.error(f"Failed to update CONFIG_PATH: {e}")

    # Delete __pycache__ directory for that plugin
    pycache_dir = os.path.join(PLUGIN_DIR, "__pycache__")

    if os.path.isdir(pycache_dir):
        try:
            shutil.rmtree(pycache_dir)
            if logger: logger.info(f"Deleted {pycache_dir}")
        except Exception as e:
            if logger: logger.error(f"Failed to delete {pycache_dir}: {e}")
