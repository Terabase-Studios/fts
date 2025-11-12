"""
FTS Improved Chat Plugin

Description:
This plugin improves the FTS chat by adding several quality-of-life improvements:
- Treats double spaces as line breaks, allowing formating messages across multiple lines easily.
- Makes recent input history persistent across restarts, so you can quickly recall previous messages.
- Unifies sender colors across sessions, ensuring each user has a consistent color for easier readability.

How it works:
- Hooks into chat message sending and receiving to modify messages and input history.
- Splits messages by double spaces to create multiple lines.
- Loads and saves recent input history to a JSON file.
- Normalizes existing chat history colors based on sender names, keeping colors consistent across restarts.

Why use it:
- Provides a cleaner, more readable chat interface.
- Simplifies formatting long messages.
- Keeps your chat history visually consistent.
- Saves your input history, for reference to common inputes.

Usage:
- Place this plugin in your FTS plugin directory.
"""

BOOT_PRIORITY = 1

import functools
import types
from typing import Callable
import os
import json
import re
import random
import colorsys

import fts.app.frontend.chat as chat
from fts.app.config import PLUGIN_DIR
from textual.widgets import RichLog, Input

from fts.app.backend.chat import send, CHAT_KEY
from fts.app.backend.commands import execute
from fts.app.backend.contacts import replace_with_contact
from fts.app.config import CHAT_FILE

INPUT_HISTORY_FILE = os.path.join(PLUGIN_DIR, "improved_chat_input_history.json")

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


def color_for_sender(sender: str) -> str:
    """Return a deterministic bright color for each unique sender."""
    # Create a stable RNG seeded by the sender string
    seed = hash(sender) & 0xFFFFFFFF  # ensure it's positive and fits 32 bits
    rng = random.Random(seed)

    # Choose hue deterministically; fix saturation and brightness for readability
    hue = rng.random()
    sat = 0.75
    val = 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def normalize_colors(filepath):
    """
    Loads chat history from a JSON file, normalizes sender colors,
    and saves it back to the file.
    """
    # Load JSON chat history
    with open(filepath, "r", encoding="utf-8") as f:
        chat_history = json.load(f)

    # Regex to match [bold #hex]name:[/bold #hex] at the start of a message
    pattern = re.compile(r'^\[bold #[0-9a-fA-F]{6}\](.+?):\[/bold #[0-9a-fA-F]{6}\]')

    new_history = []
    for message in chat_history:
        match = pattern.match(message)
        if match:
            name = match.group(1)
            color = color_for_sender(name)
            message = pattern.sub(f"[bold {color}]{name}:[/bold {color}]", message)
        new_history.append(message)

    # Save normalized chat history back
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(new_history, f, ensure_ascii=False, indent=2)

original_on_mount = None
original_send_message = None

def on_mount(self) -> None:
    global original_on_mount
    original_on_mount(self)
    try:
        with open(INPUT_HISTORY_FILE, "r") as f:
            self.history = json.load(f)
    except:
        pass

def send_message(self) -> None:
    global original_send_message
    try:
        with open(CHAT_FILE, "r") as f:
            self.lines = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        self.lines = []

    original_send_message(self)
    with open(INPUT_HISTORY_FILE, "w") as f:
        f.write(json.dumps(self.history))

def on_udp_message(self, data: bytes, addr):
    log = self.query_one(RichLog)
    if not data.startswith(CHAT_KEY):
        return  # ignore non-chat packets

    message = data[len(CHAT_KEY):].decode("utf-8", errors="ignore")
    sender = replace_with_contact(addr[0])
    color = self.color_for_sender(sender)

    # Split message on double spaces to treat as new lines
    parts = message.split("  ")

    # Prepend sender only once
    first_line = f"[bold {color}]{sender}:[/bold {color}] {parts[0]}"
    log.write(first_line)
    self.lines.append(first_line)

    # Remaining lines (without sender)
    for part in parts[1:]:
        log.write(part)
        self.lines.append(part)

    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump(self.lines, f, ensure_ascii=False, indent=2)

def new_send_message(self):
    chat_input = self.query_one("#chatinput", Input)
    msg = chat_input.value.strip()
    log = self.query_one(RichLog)

    if not msg:
        return  # ignore empty messages

    # Add to history (avoid duplicates if identical to last)
    if not self.history or self.history[-1] != msg:
        self.history.append(msg)
    self.history_index = None  # reset navigation position

    is_command, command_response = execute(msg)

    if is_command:
        # Command recognized
        if command_response.strip("-").strip() == "CLEAR FTS LOG WINDOW":
            log.clear()
            self.lines = []
            with open(CHAT_FILE, "w") as f:
                json.dump(self.lines, f)
        else:
            new_lines = command_response.strip().split("  ")
            for line in new_lines:
                log.write(line)
    elif msg.startswith("!"):
        # Command-like input but not valid
        log.write(f"[yellow]Unknown command:[/yellow] {msg}")
    else:
        # Regular message
        error = send(msg)
        if error:
            log.write(f"[red]Error:[/red] {error}")

    chat_input.clear()

def setup_plugin():
    global original_send_message, original_on_mount
    try:
        normalize_colors(CHAT_FILE)
    except FileNotFoundError:
        pass
    chat.Chat.on_udp_message = on_udp_message
    chat.Chat._send_message = new_send_message
    original_on_mount = copy_func(chat.Chat.on_mount)
    original_send_message = copy_func(new_send_message)
    chat.Chat.on_mount = on_mount
    chat.Chat._send_message = send_message
