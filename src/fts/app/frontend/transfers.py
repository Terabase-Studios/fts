import asyncio

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Vertical, HorizontalScroll
from textual.widgets import Collapsible, Label, Button, ProgressBar, Log

from fts.app.backend.contacts import replace_with_contact
from fts.app.backend.history import get_history
from fts.app.config import LOGS
from fts.utilities import format_bytes


class ActiveEntry(Container):
    def __init__(self, entry, transfer, manager):
        super().__init__()
        self.entry = entry
        self.entry_id = transfer.entry_id
        self.transfer = transfer
        self.manager = manager
        self.progress_timer = None
        self.label = None
        transfer.transfer_ui = self

    def compose(self) -> ComposeResult:
        state = self.manager.state if self.manager.state else "awaiting"
        heading = f"| {state}: {self.manager.type}, {self.entry.name} ({format_bytes(self.entry.size)}) -> {replace_with_contact(self.entry.target)}:{self.entry.port}"
        with HorizontalScroll(id="inactive_bar") as scroll:
            yield Button("cancel", variant="error", id="cancel_entry")
            self.label = Label(heading, id="inactive_entry")
            yield self.label

        progressbar = ProgressBar()
        progressbar.styles.width = "100%"
        yield progressbar

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_entry":
            self.transfer.cancelled.set()
            self.manager.cancelled = True
            self.remove()

    def on_mount(self) -> None:
        self.progress_timer = self.set_interval(1 / 10, self.make_progress)

    def make_progress(self) -> None:
        """Called automatically to advance the progress bar."""
        if self.manager.max_progress and self.manager.progress:
            progress = self.query_one(ProgressBar)
            progress.update(total=self.manager.max_progress, progress=self.manager.progress)

        state = self.manager.state if self.manager.state else "awaiting"
        self.label.update(
            f"| {state}: {self.manager.type}, {self.entry.name} "
            f"({format_bytes(self.entry.size)}) -> {replace_with_contact(self.entry.target)}:{self.entry.port}"
        )


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
        lines = entry.get("lines", [])
        with Collapsible(title=heading, id="logtab"):
            log = Log(id="logview")
            for line in lines:
                log.write(line+"\n")
            yield log


class Transfers(Container):
    def compose(self) -> ComposeResult:
        self.transfer_count = 0
        with VerticalScroll(id="transferscroll"):
            with Collapsible(title="Active", collapsed=False):
                #yield Label("Current transfers will show up here")
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
        self.inactive.mount(InactiveEntry(entry=entry, transfer=transfer), before=0)

    def add_active(self, entry, transfer, manager):
        self.active.mount(ActiveEntry(entry=entry, transfer=transfer, manager=manager), before=0)

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

    #if not history and (old_entry_ids or first_run):
    #    await container.mount(Label("Past transfers will show up here"))

    # Adjust height dynamically
    container.styles.height = max(((len(container.children)-1) * 15) + 1, 30)
