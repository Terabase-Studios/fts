"""
FTS Chat-Only Plugin

Description:
This plugin modifies FTS to run in "chat-only" mode, focusing entirely on the chat interface and contacts list.
It disables other TUI components and features, leaving you with just you, your contacts, and dreams.

How it works:
- Replaces the default FTS layout with a horizontal split: Contacts on the left (20%) and Chat on the right (80%).
- Provides a toggle command !chat_only_toggle to switch between chat-only mode and normal mode. The change takes effect after restarting FTS.

Why use it:
- Simplifies the FTS interface if you just chat functionality.
- Reduces distractions and focuses on messaging and contact discovery.
- Makes the chat bigger and more readable.

Usage:
- Place this plugin in your FTS plugin directory.
- Restart FTS to enter chat-only mode (enabled by default).
- Use !chat_only_toggle to switch between chat-only mode and normal after a restart.
"""

from textual.app import ComposeResult
import os
import sys

from textual.app import ComposeResult
from textual.containers import Horizontal

import fts.app.backend.commands as commands
import fts.app.main as app
import fts.py as fts
from fts.app.backend.contacts import start_discovery_responder
from fts.app.config import LOG_FILE
from fts.app.config import PLUGIN_DIR
from fts.app.frontend.chat import Chat
from fts.app.frontend.contacts import Contacts

DISABLED_FILE = os.path.join(PLUGIN_DIR, "chat_only_disabled.txt")

def compose_chat_only(self) -> ComposeResult:
    # yield Header()
    # yield Footer()

    with Horizontal(id="toprow") as row:
        contacts = Contacts(id="toprowa")
        chat =  Chat(id="bottomrowa")

        row.styles.height = "1fr"
        contacts.styles.width = "20%"
        chat.styles.width = "80%"

        yield contacts
        yield chat

    fts.logger = LOG_FILE
    start_discovery_responder()

async def quit(self) -> None:
    sys.exit()

def _toggle(cmd: str):
    if os.path.exists(DISABLED_FILE):
        os.remove(DISABLED_FILE)
        return "Next boot will be chat-only"
    else:
        with open(DISABLED_FILE, "w") as file:
            file.write("This file tells ChatOnly to boot in normal mode")
        return "Next boot will be normal"

def setup_plugin():
    if not os.path.exists(DISABLED_FILE):
        app.FTSApp.compose = compose_chat_only
        app.FTSApp.action_quit = quit

    commands.COMMANDS["!chat_only_toggle"] = ("\tUsage: !chat_only_toggle\n\tToggle chat only mode. Affective after restart", _toggle)
    commands.COMMAND_KEYS.append("!chat_only_toggle")