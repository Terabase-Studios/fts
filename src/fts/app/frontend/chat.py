import colorsys
import random

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import RichLog, Input, Button

from fts.app.backend.chat import send, CHAT_KEY, CHAT_PORT, start_chat_listener
from fts.app.backend.contacts import replace_with_contact, get_users


class Chat(Container):
    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, id="chatbox")

        with Horizontal(id="chatbar"):
            yield Input(id="chatinput", placeholder="Type a message and press Enter...")
            yield Button("->", variant="primary", id="chatsend")

    def on_mount(self) -> None:
        # populate map for replace_with_contacts()
        get_users()
        log = self.query_one(RichLog)
        log.write("[bold green]Write a message to send!")
        log.write("---------------------------------------")

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
        log.write(f"[bold {color}]{sender}:[/bold {color}] {message}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "chatsend":
            self._send_message()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chatinput":
            self._send_message()

    def _send_message(self):
        input = self.query_one("#chatinput", Input)
        msg = input.value

        if msg:
            log = self.query_one(RichLog)
            error = send(msg)
            if error:
                log.write(f"[red]Error:[/red] {error}")
            else:
                input.clear()
