from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container
from textual.widget import Widget
import asyncio
from textual.widgets import Collapsible, Label

from fts.app.config import LOGS
from fts.app.backend.history import get_history

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


class Transfer(Container):
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="transferscroll"):
            with Collapsible(title="Active", collapsed=False):
                yield Label("Current transfers will show up here")

            # History section
            with Collapsible(title="History", collapsed=False, id="history"):
                self.history_container = Container()
                yield self.history_container

    async def on_mount(self):
        if self.history_container:
            # Run once immediately
            asyncio.create_task(reload_history(self.history_container))

            # Auto-refresh every 5 seconds
            async def refresh_loop():
                while True:
                    await asyncio.sleep(1)
                    await reload_history(self.history_container)

            asyncio.create_task(refresh_loop())

async def reload_history(container: Container, logs_file=LOGS):
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

    if not history:
        await container.mount(Label("Past transfers will show up here"))

    # Adjust height dynamically
    container.styles.height = max(len(container.children) * 15, 30)
