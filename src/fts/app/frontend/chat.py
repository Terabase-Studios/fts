import colorsys
import json
import random

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.suggester import SuggestFromList
from textual.widgets import RichLog, Input, Button

from fts.app.backend.chat import send, CHAT_KEY, CHAT_PORT, start_chat_listener
from fts.app.backend.commands import COMMAND_KEYS, execute
from fts.app.backend.contacts import replace_with_contact, get_users
from fts.app.config import CHAT_FILE


class Chat(Container):
    def __init__(self, *args, **kwargs) -> None:
        try:
            with open(CHAT_FILE, "r") as f:
                self.lines = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.lines = []

        # Command/message history
        self.history: list[str] = []
        self.history_index: int | None = None

        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, id="chatbox")

        with Horizontal(id="chatbar"):
            yield Input(id="chatinput", placeholder="Type a message and press Enter...", suggester=SuggestFromList(COMMAND_KEYS))
            yield Button("->", variant="primary", id="chatsend")

    def on_mount(self) -> None:
        # populate map for replace_with_contacts()
        get_users()
        log = self.query_one(RichLog)
        log.write("[bold green]Write a message to send! Send !help for list of commands!")
        log.write("---------------------------------------")
        for line in self.lines:
            log.write(line)

        # Start UDP listener here
        start_chat_listener(self.app, CHAT_PORT, self.on_udp_message)

    def color_for_sender(self, sender: str) -> str:
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

    def on_udp_message(self, data: bytes, addr):
        log = self.query_one(RichLog)
        if not data.startswith(CHAT_KEY):
            return  # ignore non-chat packets

        message = data[len(CHAT_KEY):].decode("utf-8", errors="ignore")
        sender = replace_with_contact(addr[0])

        color = self.color_for_sender(sender)
        line = f"[bold {color}]{sender}:[/bold {color}] {message}"
        log.write(line)
        self.lines.append(line)

        with open(CHAT_FILE, "w") as f:
            json.dump(self.lines, f)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "chatsend":
            self._send_message()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chatinput":
            self._send_message()

    def _send_message(self):
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
                log.write(command_response)
        elif msg.startswith("!"):
            # Command-like input but not valid
            log.write(f"[yellow]Unknown command:[/yellow] {msg}")
        else:
            # Regular message
            error = send(msg)
            if error:
                log.write(f"[red]Error:[/red] {error}")

        chat_input.clear()

    def on_key(self, event: events.Key) -> None:
        """Handle arrow key history navigation."""
        chat_input: Input = self.query_one("#chatinput", Input)

        if event.key == "up":
            if not self.history:
                return
            if self.history_index is None:
                self.history_index = len(self.history) - 1
            else:
                self.history_index = max(0, self.history_index - 1)
            chat_input.value = self.history[self.history_index]
            chat_input.cursor_position = len(chat_input.value)

        elif event.key == "down":
            if self.history_index is None:
                return
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
                chat_input.value = self.history[self.history_index]
            else:
                # Reset to empty input
                chat_input.value = ""
                self.history_index = None
            chat_input.cursor_position = len(chat_input.value)
