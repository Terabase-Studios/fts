import textwrap

from fts.app.backend.plugins.installer import fetch_manifest, list_available_plugins
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
            list_plugins()
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