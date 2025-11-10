import configparser
import importlib.util
import os
import time
import traceback

from fts.app.config import PLUGIN_DIR, CONFIG_PATH, PLUGINS_ENABLED


def load_plugins():
    if not PLUGINS_ENABLED:
        return
    # Step 1: Create plugin directory if it doesn't exist
    os.makedirs(PLUGIN_DIR, exist_ok=True)

    # Step 2: Scan for all .py files in plugin directory
    plugin_files = [f for f in os.listdir(PLUGIN_DIR) if f.endswith(".py")]

    # Step 3: Load or create config.ini
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    if "plugins" not in config:
        config["plugins"] = {}

    # Add new plugins to config with default enabled=True if not already present
    for plugin_file in plugin_files:
        plugin_name = plugin_file[:-3]  # remove .py

        if plugin_name not in config["plugins"]:
            config["plugins"][plugin_name] = "true"

    # Save updated config
    with open(CONFIG_PATH, "w") as f:
        config.write(f)

    # Step 4: Import enabled plugins and run setup
    loaded_plugins = {}
    for plugin_name, enabled in config["plugins"].items():
        if enabled.lower() != "true":
            continue

        plugin_path = os.path.join(PLUGIN_DIR, plugin_name + ".py")
        if not os.path.exists(plugin_path):
            print(f"[PLUGIN WARN] {plugin_name} not found in plugin directory.")
            continue

        try:
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded_plugins[plugin_name] = module

            # Run setup() if it exists
            if hasattr(module, "setup"):
                module.setup()
            print(f"[PLUGIN LOADED] {plugin_name}")
        except Exception as e:
            print(f"[PLUGIN ERROR] Failed to load {plugin_name}: {e}")
            traceback.print_exc()
            try:
                time.sleep(3)
            except KeyboardInterrupt:
                pass