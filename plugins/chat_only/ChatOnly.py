"""
FTS Chat-Only Plugin

Description:
This plugin modifies FTS to run in "chat-only" mode, focusing entirely on the chat interface and contacts list.
It disables other TUI components and features, leaving you with just you, your contacts, and dreams.

How it works:
- Replaces the default FTS layout with a horizontal split: Contacts on the left (20%) and Chat on the right (80%).
- Provides a toggle command !chat_only_toggle to switch between chat-only mode and normal mode. The change takes immediately.

Why use it:
- Simplifies the FTS interface if you just chat functionality.
- Reduces distractions and focuses on messaging and contact discovery.
- Makes the chat bigger and more readable.

Usage:
- Place this plugin in your FTS plugin directory.
- The FTS TUI defaults to chat-only.
- Use !chat_only_toggle to switch between chat-only mode and normal immediately.
"""

import os

from textual.app import ComposeResult
from textual.containers import Horizontal

import fts.app.backend.commands as commands
import fts.app.main as app
import fts.py as fts
from fts.app.backend.contacts import start_discovery_responder
from fts.app.config import LOG_FILE, PLUGIN_DIR
from fts.app.frontend.chat import Chat
from fts.app.frontend.contacts import Contacts

DISABLED_FILE = os.path.join(PLUGIN_DIR, "chat_only_disabled.txt")

compose_all = None
original_on_mount = None


def compose_chat_only() -> ComposeResult:
    with Horizontal(id="toprow") as row:
        contacts = Contacts(id="toprowa")
        chat = Chat(id="bottomrowa")

        row.styles.height = "1fr"
        contacts.styles.width = "20%"
        chat.styles.width = "80%"

        yield contacts
        yield chat

    fts.logger = LOG_FILE
    start_discovery_responder()


def _toggle(cmd: str):
    running_app = app.fts_app

    if os.path.exists(DISABLED_FILE):
        os.remove(DISABLED_FILE)
        focus_chat(running_app)
        return "Switching to chat-only mode"
    else:
        with open(DISABLED_FILE, "w") as file:
            file.write("This file tells ChatOnly to boot in normal mode")
        unfocus_chat(running_app)
        return "Switching to normal mode"


def focus_chat(self) -> None:
    self.compose = compose_chat_only

    # Force Textual to rebuild everything.
    self.call_later(self.refresh)
    self.call_later(self.recompose)


def unfocus_chat(self) -> None:
    global compose_all
    self.compose = compose_all
    self.call_later(self.refresh)
    self.call_later(self.recompose)


def on_mount(self) -> None:
    global original_on_mount
    original_on_mount(self)
    if not os.path.exists(DISABLED_FILE):
        focus_chat(self)


def setup_plugin():
    global original_on_mount, compose_all

    compose_all = app.FTSApp.compose
    original_on_mount = app.FTSApp.on_mount

    app.FTSApp.on_mount = on_mount

    commands.COMMANDS["!chat_only_toggle"] = (
        "\tUsage: !chat_only_toggle\n\tToggle chat-only mode. Effective after restart",
        _toggle,
    )
    commands.COMMAND_KEYS.append("!chat_only_toggle")
