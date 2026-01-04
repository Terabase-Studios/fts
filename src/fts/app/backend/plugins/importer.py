import configparser
import importlib.util
import os
import time
import traceback

from fts.app.backend.plugins.verifier import verify_plugins
from fts.app.backend.plugins.config import SECURE, ERROR_FREEZE_TIME
from fts.app.config import PLUGIN_DIR, CONFIG_PATH, PLUGINS_ENABLED

DEFAULT_PRIORITY = 5  # Default boot priority if plugin doesn't define BOOT_PRIORITY

def load_plugins():
    if not PLUGINS_ENABLED:
        return

    os.makedirs(PLUGIN_DIR, exist_ok=True)
    unverified_plugin_files = [f for f in os.listdir(PLUGIN_DIR) if f.endswith(".py") and "no_include" not in f]
    if not unverified_plugin_files:
        return

    if SECURE and unverified_plugin_files:
        print("[PLUGIN VERIFIER] Verifying plugins...")
        plugin_files = verify_plugins(unverified_plugin_files)
    else:
        plugin_files = unverified_plugin_files

    # Load or create config.ini
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    if "plugins" not in config:
        config["plugins"] = {}

    # Add new plugins to config with default enabled=True
    for plugin_file in plugin_files:
        plugin_name = plugin_file[:-3]  # remove .py
        if plugin_name not in config["plugins"]:
            answer = input(f"Do you want to enable the plugin '{plugin_name}'? [Y/n]: ").strip().lower()
            config["plugins"][plugin_name] = "false" if answer.lower().strip() == "n" or answer.lower().strip() == "no" else "true"

    with open(CONFIG_PATH, "w") as f:
        config.write(f)

    # Step 4: Import enabled plugins
    loaded_plugins = []
    allowed = {pf[:-3].lower() for pf in plugin_files}

    for plugin_name, enabled in config["plugins"].items():
        if enabled.lower().strip() != "true":
            continue
        if plugin_name not in allowed:
            print(f"[PLUGIN ERROR] {plugin_name} is corrupted or out of date!\nRun `fts plugins upgrade -f` to reinstall all plugins.")
            time.sleep(ERROR_FREEZE_TIME)
            continue

        normalized_name = plugin_name.lower() + ".py"
        plugin_path = next((os.path.join(PLUGIN_DIR, f) for f in os.listdir(PLUGIN_DIR) if f.lower() == normalized_name), None)

        if not plugin_path or not os.path.exists(plugin_path):
            print(f"[PLUGIN WARN] {plugin_name} not found in plugin directory.")
            continue

        try:
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Determine boot priority
            priority = getattr(module, "BOOT_PRIORITY", DEFAULT_PRIORITY)
            loaded_plugins.append((priority, plugin_name, module))

        except Exception as e:
            print(f"[PLUGIN ERROR] Failed to load {plugin_name}: {e}")
            traceback.print_exc()
            try:
                time.sleep(ERROR_FREEZE_TIME)
            except KeyboardInterrupt:
                pass

    # Sort by priority (highest last)
    loaded_plugins.sort(key=lambda x: x[0])

    # Run setup_plugin in boot order
    for _, plugin_name, module in loaded_plugins:
        try:
            if hasattr(module, "setup_plugin"):
                module.setup_plugin()
                print(f"[PLUGIN LOADED] {plugin_name}")
            else:
                print(f"[PLUGIN ERROR] {plugin_name} has no setup_plugin method.")
                try:
                    time.sleep(ERROR_FREEZE_TIME)
                except KeyboardInterrupt:
                    pass
        except Exception as e:
            print(f"[PLUGIN ERROR] setup_plugin failed for {plugin_name}: {e}")
            traceback.print_exc()
            try:
                time.sleep(ERROR_FREEZE_TIME)
            except KeyboardInterrupt:
                pass