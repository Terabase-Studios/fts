"""
FTS Blacklist Plugin

Description:
This plugin removes a list of ips from your fts TUI!
It is designed to prevent connections to unwanted hosts, suspicious devices, or potentially unsafe contacts
in your network.

How it works:
- On first run, it creates `ip_blacklist.txt` in the plugin directory if it does not exist.
- Each line in this file represents a blacklisted IP. Lines starting with '#' are treated as comments.
- When `discover()` is called, the plugin resolves contacts to their base IPs using FTS's `replace_with_ip()`
  and filters out any IPs found in the blacklist.
- Duplicate IPs are automatically ignored, and ordering is preserved.

Why use it:
- Helps prevent accidental connections to sensitive or restricted machines.
- Useful in environments where Oracle VMs or similar virtual machines might create "echo" IPs
  that appear in the TUI, cluttering results or causing unintended connections.
- Provides a simple way to manage network security directly from FTS, without modifying core code.

Optional extensions:
- Commands can be added to append or remove IPs from the blacklist at runtime.
- Works seamlessly with the FTS plugin system and preserves the original discover() behavior
  when disabled.

Usage:
- Install this plugin in your FTS plugin directory.
- Edit `ip_blacklist.txt` to add any IPs you want to block.
- Use FTS as normal; `discover()` will automatically skip blacklisted IPs.

Warning: This plugin currently does not block file transfer requests!
"""

import functools
import json
import os
import types
from typing import Any, Callable

import fts.app.backend.contacts as fts_contacts
import fts.app.config as config
from fts.app.backend.chat import MUTED_USERS
from fts.app.backend.contacts import replace_with_ip, get_seen_users
from fts.app.config import SEEN_IPS_FILE

BLACKLIST_FILE = os.path.join(config.PLUGIN_DIR, "ip_blacklist.txt")
blacklist = None

def copy_func(f: Callable) -> Callable:
    g = types.FunctionType(
        f.__code__,
        f.__globals__,
        name=f.__name__,
        argdefs=f.__defaults__,
        closure=f.__closure__
    )
    g = functools.update_wrapper(g, f)
    g.__kwdefaults__ = getattr(f, "__kwdefaults__", None)
    return g

# Store original function
base_discover = copy_func(fts_contacts.discover)

def load_blacklist() -> set[Any] | str | list[str]:
    """Load IPs from blacklist file. Create file if missing."""
    if not os.path.exists(BLACKLIST_FILE):
        # Create empty file
        with open(BLACKLIST_FILE, "w") as f:
            f.write("# Add one IP per line to blacklist\n#Contacts are resolved to there based ip, based on contacts.json\n")
        return set()
    with open(BLACKLIST_FILE, "r") as f:
        # Ignore comments and empty lines
        lines = []
        seen = set()
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line in seen:
                continue
            seen.add(line)
            lines.append(line)
        return replace_with_ip(lines)

def blacklister(*args, timeout: float = 0.5, **kwargs) -> list[Any] | None:
    """Wrapped discover() that filters blacklisted IPs."""
    global blacklist
    try:
        results = base_discover(*args, **kwargs)
        filtered = [r for r in results if r not in blacklist]
        return filtered
    except Exception as e:
        return None

def setup():
    """Patch FTS discover() with blacklister."""
    global blacklist
    fts_contacts.discover = blacklister
    blacklist = load_blacklist()

    # mute blacklisted
    muted = MUTED_USERS.get_muted()
    muted += blacklist
    MUTED_USERS.set_muted(muted)

    # remove seen blacklisted
    seen_users = get_seen_users()
    seen_users = [r for r in seen_users if r not in blacklist]
    with open(SEEN_IPS_FILE, "w") as f:
        json.dump(seen_users, f)

