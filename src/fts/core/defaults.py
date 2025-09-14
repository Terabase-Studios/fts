import json
from argparse import Namespace
from pathlib import Path

from fts.config import DEFAULTS_FILE


def cmd_save(args, logger):
    logger.debug(f"Options: {args}")
    defaults = args
    try:
        logger.debug("Converting arguments to dictionary")
        defaults = sterilize_namespace(defaults)
    except Exception as e:
        logger.error(f"Failed to convert arguments to dictionary: {e}")

    logger.debug(f"Defaults: {defaults}")
    try:
        save_defaults(defaults)
        logger.info(f"Saved defaults")
    except Exception as e:
        logger.error(f"Failed to save defaults: {e}")


def save_defaults(defaults, path: Path = DEFAULTS_FILE) -> None:
    """Save defaults dictionary to JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(defaults, f, indent=2)


def load_defaults(path: Path = DEFAULTS_FILE) -> dict:
    """Load defaults dictionary from JSON file (empty dict if none)."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Ignore Bad file
        return {}

def sterilize_namespace(namespace: Namespace) -> dict:
    key_filter = ['command', 'quiet', 'verbose', 'func']

    dictionary = {}
    for key, value in namespace.__dict__.items():
        if isinstance(value, Namespace):
            dictionary[key] = sterilize_namespace(value)

        else:
            if str(key) not in key_filter:
                if value is not int and value is not float:
                    value = str(value)

                dictionary[key] = value

    return dictionary