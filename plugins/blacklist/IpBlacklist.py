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

import json
import os
from typing import Any

import fts.app.backend.commands as commands
import fts.app.backend.contacts as fts_contacts
import fts.app.config as config
from fts.app.backend.chat import MUTED_USERS
from fts.app.backend.commands import _get_second_arg
from fts.app.backend.contacts import replace_with_ip, get_seen_users, replace_with_contact
from fts.app.backend.plugins.utils import copy_func
from fts.app.config import SEEN_IPS_FILE

BLACKLIST_FILE = os.path.join(config.PLUGIN_DIR, "ip_blacklist.txt")
blacklist = []


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

def setup_plugin():
    """Patch FTS discover() with blacklister."""
    global blacklist
    fts_contacts.discover = blacklister
    blacklist = replace_with_ip(load_blacklist())

    # mute blacklisted
    muted = MUTED_USERS.get_muted()
    muted += blacklist
    MUTED_USERS.set_muted(list(set(muted)))

    # remove seen blacklisted
    seen_users = get_seen_users()
    seen_users = [r for r in seen_users if r not in blacklist]
    with open(SEEN_IPS_FILE, "w") as f:
        json.dump(seen_users, f)

    load_commands()


def _blacklist(cmd: str):
    global blacklist
    ip = _get_second_arg(cmd)
    ip = replace_with_ip(ip)
    users = replace_with_ip(get_seen_users())
    if ip not in users:
        return "IP is not a valid user"

    blacklist.append(ip.strip())

    # mute blacklisted
    muted = MUTED_USERS.get_muted()
    muted += blacklist
    MUTED_USERS.set_muted(list(set(muted)))

    # remove seen blacklisted
    seen_users = get_seen_users()
    seen_users = [r for r in seen_users if r not in blacklist]
    with open(SEEN_IPS_FILE, "w") as f:
        json.dump(seen_users, f)

    update_blacklist()

    return f"Blacklisted {replace_with_contact(ip)}"

def _unblacklist(cmd: str):
    global blacklist
    ip = _get_second_arg(cmd)
    ip = replace_with_ip(ip)
    if ip not in blacklist:
        return "IP is not blacklisted"

    blacklist.pop(blacklist.index(ip.strip()))
    update_blacklist()

    return f"Unblacklisted {replace_with_contact(ip)}\nYou need to manually unmute them with `!unmute`\nThe user will not appear until the next time they are online"

def _blacklisted(cmd: str):
    global blacklist
    if blacklist:
        return "Blacklisted:\n\t" + "\n\t".join(replace_with_contact(blacklist))
    else:
        return "No users blacklisted."


def update_blacklist():
    """Replace all IPs/contacts in the blacklist while preserving the top comments."""
    global blacklist
    with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    header = []
    for line in lines:
        if line.lstrip().startswith("#"):
            header.append(line.rstrip('\n'))
        else:
            break

    # Clean user entries
    user_lines = [str(u).strip() for u in blacklist if str(u).strip()]

    # Write back header + new entries
    with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
        for h in header:
            f.write(h + '\n')
        for u in user_lines:
            f.write(u + '\n')


def load_commands() -> None:
    commands.COMMANDS["!blacklisted"] = ("\tUsage: !blacklisted ip\n\tlist blacklisted users", _blacklisted)
    commands.COMMAND_KEYS.append("!blacklisted")
    commands.COMMANDS["!blacklist"] = ("\tUsage: !blacklist ip\n\tban a user from your fts TUI", _blacklist)
    commands.COMMAND_KEYS.append("!blacklist")
    commands.COMMANDS["!unblacklist"] = ("\tUsage: !unblacklist ip\n\tre-add a user to your fts TUI", _unblacklist)
    commands.COMMAND_KEYS.append("!unblacklist")


