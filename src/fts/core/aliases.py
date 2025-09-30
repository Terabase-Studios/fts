import json
import logging
import os
import re
from pathlib import Path

from fts.config import ALIASES_FILE


# --- Add / List / Remove Aliases ---
def cmd_alias(args, logger):
    aliases = load_aliases(logger)

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
        return

    # --- Add ---
    if args.action == "add":
        if not args.name or not args.value or not args.type:
            logger.error("Must provide both 'name', 'value', and 'type' to add an alias.")
            return

        if args.type not in ("ip", "dir"):
            logger.error("Alias type must be 'ip' or 'dir'")
            return

        warn_invalid = False
        # Validate syntax
        if args.type == "ip":
            ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
            if not re.match(ip_pattern, args.value):
                logger.warning(f"Potentially invalid IP address format: {args.value}")
                warn_invalid = True

            if not warn_invalid:
                octets = args.value.split(".")
                if any(int(o) > 255 for o in octets):
                    logger.error(f"IP address has octet > 255: {args.value}")
                    return
        elif args.type == "dir":
            invalid_chars = '<>\"|?*'
            if any(c in args.value for c in invalid_chars):
                logger.error(f"Directory alias contains invalid characters: {args.value}")
                return
            if os.path.isabs(args.value):
                args.value = os.path.normpath(args.value)

            # Warn if path seems questionable
            if not os.path.exists(args.value):
                logger.warning(f"Directory path does not exist: {args.value}")
                warn_invalid = True

        # Check for overwrite
        overwriting = args.name in aliases[args.type]

        # Ask user to continue unless --yes was given
        if not args.yes:
            if warn_invalid:
                resp = input(f"Value '{args.value}' may be invalid. Continue adding alias? [y/N]: ")
                if resp.lower() != "y":
                    logger.info("Alias not added.")
                    return
            if overwriting:
                resp = input(f"Alias '{args.name}' already exists and will be overwritten. Continue? [y/N]: ")
                if resp.lower() != "y":
                    logger.info("Alias not added.")
                    return

        aliases[args.type][args.name] = args.value
        _save_aliases(aliases, logger)
        logger.info(f"Alias added: {args.name} -> {args.value} ({args.type})")
        return

    # --- Remove ---
    if args.action == "remove":
        if not args.name or not args.type:
            logger.error("Must provide both 'name' and 'type' to remove an alias.")
            return

        if args.type not in ("ip", "dir"):
            logger.error("Alias type must be 'ip' or 'dir'")
            return

        found = False
        if args.name in aliases[args.type]:
            del aliases[args.type][args.name]
            found = True

        if found:
            _save_aliases(aliases, logger)
            logger.info(f"Alias '{args.name}' removed")
        else:
            logger.warning(f"No alias named '{args.name}' found")
        return


# --- Load / Save Aliases ---
def load_aliases(logger=None):
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


def resolve_args(args, logger: logging.Logger):
    if getattr(args, "output", None):
        args.output = resolve_alias(args.output, "dir", logger=logger)
    if getattr(args, "path", None):
        args.path = resolve_alias(args.path, "dir", logger=logger)
    if getattr(args, "ip", None):
        args.ip = resolve_alias(args.ip, "ip", logger=logger)
    return args

# --- Resolve alias to actual path or IP ---
def resolve_alias(path_or_alias: str, type_: str, logger: logging.Logger):
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

    aliases = load_aliases(logger)

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

def reverse_resolve_alias(value: str, type_: str, logger=None):
    """
    Reverse lookup for aliases.

    For IPs: if value matches an IP alias, return alias name, else return original IP.
    For dirs: if value starts with a directory alias base, return alias + subpath.

    :param value: IP or path string
    :param type_: "ip" or "dir"
    :param logger: optional logger
    :return: alias name (or alias/subpath) if found, else original value
    """
    if logger is None:
        logger = logging.getLogger("fts")

    aliases = load_aliases(logger)

    if type_ == "ip":
        for name, ip in aliases["ip"].items():
            if value == ip:
                return name
        return value

    elif type_ == "dir":
        value_path = Path(value).resolve()
        for alias_name, base_path in aliases["dir"].items():
            base_path = Path(base_path).resolve()
            try:
                relative = value_path.relative_to(base_path)
                # Found a matching alias, return alias + subpath
                return str(Path(alias_name) / relative)
            except ValueError:
                continue
        return value

    else:
        logger.error(f"Invalid type '{type_}' for reverse alias resolution.")
        return value