import sys

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, HorizontalGroup, Container, Vertical
from textual.events import MouseScrollUp, MouseScrollDown
from textual.reactive import reactive
from textual.widgets import Footer, Header, Collapsible, Label, Log
from fts.app.transfers.history import get_history
from fts.app.config import LOGS


class LogEntry(Container):
    def __init__(self, entry):
        super().__init__()
        self.entry = entry
        if self.entry["status"] == "success":
            self.add_class("success")
        elif self.entry["status"] == "error":
            self.add_class("error")

    def compose(self) -> ComposeResult:
        entry = self.entry
        heading = f"{entry['start_time']}> {entry['type']}, {entry['file']}"
        text = "\n".join(entry.get("lines", []))  # put all lines together
        with Collapsible(title=heading, id="logtab"):
            yield Label(text, id="logview")


class Transfer(Container):
    def compose(self) -> ComposeResult:
        # Active section
        with VerticalScroll(id="transferscroll"):
            with Collapsible(title="Active", collapsed=False):
                yield Label("Current transfers will show up here")

            # History section
            with Collapsible(title="History", collapsed=False, id="history") as collapsed:
                history = get_history(LOGS)
                if not history:
                    yield Label("Past transfers will show up here")
                else:
                    for entry in history:
                        yield LogEntry(entry)

                collapsed.styles.height = len(history) * 15

