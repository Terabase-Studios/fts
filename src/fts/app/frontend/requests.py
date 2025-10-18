from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Vertical, Horizontal
from textual.widgets import Label, Button, Rule, Log

from fts.app.backend.contacts import replace_with_contact
from fts.utilities import format_bytes


class Request(Vertical):
    def __init__(self, *args, entry, transfer):
        super().__init__(*args)
        self.entry = entry
        self.entry_id = transfer.entry_id
        self.transfer = transfer
        transfer.request_ui = self

    def compose(self) -> ComposeResult:
        with Container(id="requests_container"):
            yield Log(id="request_log")

            with Horizontal(id='request_button_bar'):
                yield Button("Accept", variant="success", id="request_accept")
                yield Button("Deny", variant="error", id="request_deny")

    def _on_mount(self, event: events.Mount) -> None:
        log = self.get_widget_by_id("request_log")
        log.write_line(f"Received request from: {replace_with_contact(self.entry.target)}")
        log.write_line(f"Filename: {self.entry.name}")
        log.write_line(f"Size: {format_bytes(self.entry.size)}")
        log.write_line(f"Port: {self.entry.port}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        if event.button.id == "request_deny":
            self.transfer.cancelled.set()

        elif event.button.id == "request_accept":
            self.transfer.accepted.set()

        else:
            return

        self.remove()


class Requests(Container):
    def compose(self) -> ComposeResult:
        with Vertical(id="requests_header"):
            yield Label("Transfer requests", id="requests_label", expand=True)
            yield Rule(line_style="heavy")
        vertical_scroll = VerticalScroll(id="requests_scroll")
        yield vertical_scroll

    def add_request(self, entry, transfer):
        vs = self.get_widget_by_id("requests_scroll")
        req_widget = Request(entry=entry, transfer=transfer)
        vs.mount(req_widget)
        self.app.refresh()