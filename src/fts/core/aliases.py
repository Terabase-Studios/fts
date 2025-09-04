import json
import os
import sys

from fts.config import ALIASES_FILE


# --- Load / Save Aliases ---
def _load_aliases(logger=None):
    if not os.path.exists(ALIASES_FILE):
        return {"ip": {}, "dir": {}}
    try:
        with open(ALIASES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Alias file format invalid")
        data.setdefault("ip", {})
        data.setdefault("dir", {})
        return data
    except (json.JSONDecodeError, ValueError) as e:
        if logger:
            logger.warning(f"Aliases file is corrupted or invalid, using empty defaults: {e}")
        return {"ip": {}, "dir": {}}
    except Exception as e:
        if logger:
            logger.error(f"Failed to load aliases: {e}")
        return {"ip": {}, "dir": {}}

def _save_aliases(data, logger=None):
    try:
        with open(ALIASES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        if logger:
            logger.error(f"Failed to save aliases: {e}")

# --- Add / List / Remove Aliases ---
def cmd_alias(args, logger):
    aliases = _load_aliases(logger)

    # --- List ---
    if args.action == "list":
        if not aliases["ip"] and not aliases["dir"]:
            logger.info("No aliases defined yet.")
        else:
            if aliases["ip"]:
                logger.info("Devices:")
                for k, v in aliases["ip"].items():
                    logger.info(f"  {k} -> {v}")
            else:
                logger.info("No device aliases defined.")

            if aliases["dir"]:
                logger.info("Folders:")
                for k, v in aliases["dir"].items():
                    logger.info(f"  {k} -> {v}")
            else:
                logger.info("No folder aliases defined.")
        print('')
        return

    # --- Add ---
    if args.action == "add":
        if not args.name or not args.value:
            logger.error("Must provide both 'name' and 'value' to add an alias.")
            sys.exit(1)
        if args.type not in ("ip", "dir"):
            logger.error("Alias type must be 'ip' or 'dir'")
            sys.exit(1)

        # Validate syntax
        if args.type == "ip":
            ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
            if not re.match(ip_pattern, args.value):
                logger.error(f"Invalid IP address format: {args.value}")
                sys.exit(1)
            octets = args.value.split(".")
            if any(int(o) > 255 for o in octets):
                logger.error(f"IP address has octet > 255: {args.value}")
                sys.exit(1)
        elif args.type == "dir":
            # Only check for illegal characters / syntax, not existence
            invalid_chars = '<>\"|?*'
            if any(c in args.value for c in invalid_chars):
                logger.error(f"Directory alias contains invalid characters: {args.value}")
                sys.exit(1)
            if os.path.isabs(args.value):
                # Optional: enforce relative aliases
                args.value = os.path.normpath(args.value)

        aliases[args.type][args.name] = args.value
        _save_aliases(aliases, logger)
        logger.info(f"Alias added: {args.name} -> {args.value} ({args.type})")
        print('')
        return

    # --- Remove ---
    if args.action == "remove":
        if not args.name:
            logger.error("Must provide 'name' to remove an alias.")
            sys.exit(1)

        found = False
        for t in ("ip", "dir"):
            if args.name in aliases[t]:
                del aliases[t][args.name]
                found = True

        if found:
            _save_aliases(aliases, logger)
            logger.info(f"Alias '{args.name}' removed")
        else:
            logger.warning(f"No alias named '{args.name}' found")
        print('')
        return


# --- Resolve alias to actual path or IP ---
import logging
import re
from pathlib import Path

def resolve_alias(path_or_alias: str, type_: str, logger=None):
    """
    Resolve a string using aliases (IP or directory).

    For directories, allows nested paths like "test/file.txt" (appends to alias base).

    :param path_or_alias: alias name or full path / IP
    :param type_: "ip" or "dir"
    :param logger: optional logger to report warnings
    :return: resolved string if valid, else None
    """
    if logger is None:
        logger = logging.getLogger("fts")

    aliases = _load_aliases(logger)

    if type_ == "dir":
        # Split on OS separator only for the alias part
        parts = Path(path_or_alias).parts
        if not parts:
            logger.warning("Empty directory path provided.")
            return None

        base_alias = parts[0]
        sub_path = Path(*parts[1:]) if len(parts) > 1 else Path()

        # Resolve alias base
        resolved_base = Path(aliases["dir"].get(base_alias, base_alias))
        resolved_path = resolved_base / sub_path


        return str(resolved_path.resolve())

    elif type_ == "ip":
        resolved = aliases["ip"].get(path_or_alias, path_or_alias)
        ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"

        if not re.match(ip_pattern, resolved):
            logger.warning(f"IP address '{resolved}' is not valid.")
            return None

        octets = resolved.split(".")
        if any(int(o) > 255 for o in octets):
            logger.warning(f"IP address '{resolved}' has invalid octet > 255.")
            return None

        return resolved

    else:
        logger.error(f"Invalid type '{type_}' for alias resolution.")
        return None