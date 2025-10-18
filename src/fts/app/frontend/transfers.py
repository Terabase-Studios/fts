import asyncio

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Vertical, HorizontalScroll
from textual.widgets import Collapsible, Label, Button

from fts.app.backend import transfer
from fts.app.backend.contacts import replace_with_contact
from fts.app.backend.history import get_history
from fts.app.config import LOGS
from fts.utilities import format_bytes


class InactiveEntry(Container):
    def __init__(self, entry, transfer):
        super().__init__()
        self.entry = entry
        self.entry_id = transfer.entry_id
        self.transfer = transfer
        transfer.transfer_ui = self

    def compose(self) -> ComposeResult:
        entry = self.entry
        heading = f"| send, {self.entry.name} ({format_bytes(self.entry.size)}) -> {replace_with_contact(entry.target)}:{entry.port}"
        with HorizontalScroll(id="inactive_bar"):
            yield Button("cancel", variant="error", id="cancel_entry")
            yield Label(heading, id="inactive_entry")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_entry":
            self.transfer.cancelled.set()

class LogEntry(Container):
    def __init__(self, entry):
        super().__init__()
        self.entry = entry
        if self.entry["status"] == "success":
            self.add_class("success")
        elif self.entry["status"] == "error":
            self.add_class("error")
        self.entry_id = entry["id"]

    def compose(self) -> ComposeResult:
        entry = self.entry
        heading = f"{entry['start_time']}> {entry['type']}, {entry['file']}"
        text = "\n".join(entry.get("lines", []))  # put all lines together
        with Collapsible(title=heading, id="logtab"):
            yield Label(text, id="logview")


class Transfers(Container):
    def compose(self) -> ComposeResult:
        self.transfer_count = 0
        with VerticalScroll(id="transferscroll"):
            with Collapsible(title="Active", collapsed=False):
                yield Label("Current transfers will show up here")
                self.active = Vertical(id="active_container")
                self.inactive = Vertical(id="inactive_container")
                yield self.active
                yield self.inactive


            # History section
            with Collapsible(title="History", collapsed=False, id="history"):
                self.history_container = Container()
                yield self.history_container

    async def on_mount(self):
        if self.history_container:
            # Run once immediately
            asyncio.create_task(reload_history(self.history_container, first_run=True))

            # Auto-refresh every 5 seconds
            async def refresh_loop():
                while True:
                    await asyncio.sleep(1)
                    await reload_history(self.history_container)

            asyncio.create_task(refresh_loop())

    def add_inactive(self, entry, transfer):
        self.inactive.mount(InactiveEntry(entry=entry, transfer=transfer))

async def reload_history(container: Container, logs_file=LOGS, first_run=False):
    """
    Reload the History section asynchronously.
    Preserves existing LogEntry collapsibles; removes old entries; adds new ones.
    Adjusts container height dynamically.
    """
    # You can wrap get_history in asyncio.to_thread if it's blocking
    history = await asyncio.to_thread(get_history, logs_file)
    history_ids = {entry["id"] for entry in history}

    old_entry_ids = set()

    for child in list(container.children):
        if isinstance(child, LogEntry):
            old_entry_ids.add(child.entry_id)
            if child.entry_id not in history_ids:
                await child.remove()
        elif isinstance(child, Label):
            if history:
                await child.remove()

    # Add new entries at the top
    for entry in history:
        if entry["id"] not in old_entry_ids:
            await container.mount(LogEntry(entry), before=0)

    if not history and (old_entry_ids or first_run):
        await container.mount(Label("Past transfers will show up here"))

    # Adjust height dynamically
    container.styles.height = ((len(container.children)-1) * 15) + 1
