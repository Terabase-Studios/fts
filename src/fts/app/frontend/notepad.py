import sys
import os

from textual.widgets import Tree, Input, Switch, Placeholder, TextArea
from textual.widgets.tree import TreeNode
from textual.events import Key

from fts.app.backend.host import host_manager
from fts.app.backend.library import FTSLibrary, LIBRARY_PATH
from fts.app.backend.library.network import FTSNetLibrary, get_libraries, ask_for_file

import socket
import datetime

from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Vertical, Horizontal
from textual.widgets import Label, Button, Rule, Log, Collapsible

from fts.app.backend.contacts import ONLINE_USERS, replace_with_ip, replace_with_contact
from fts.app.backend.notepad import NotepadHost, NotepadClient
from fts.app.config import logger, library_enabled, set_config_value, SAVE_DIR
import fts.app.config as app_config

class NotepadWindow(Container):
    def compose(self) -> ComposeResult:
        self.text = "The notepad is currently in beta and unstable.\nIf you experience any syncing issues,\nplease press any key to resync..."
        self.text_area = TextArea(id="notepad")
        self.text_area.text = self.text
        yield self.text_area
        yield Button("Export", id="notepad_export", variant="default")

    def on_mount(self) -> None:
        # If this machine is the host
        self.host = NotepadHost()

        # Schedule client creation after mount
        self.call_later(self.start_client)

    def start_client(self):
        self.client = NotepadClient(
            on_update_callback=self.on_text_update_from_host
        )

    def on_text_area_changed(self, event):
        if getattr(self, "client", None) is None:
            return
        if getattr(self, "suppress_local_event", False):
            return

        if self.text == "The notepad is currently in beta and unstable.\nIf you experience any syncing issues,\nplease press any key to resync...":
            event.text_area.text = "​"
            self.text = "​"
            self.client.new_text("​")
            return

        new_text = event.text_area.text
        self.text = new_text
        self.client.new_text(new_text)

    def on_text_update_from_host(self, new_text):
        # Schedule the update on the main thread
        def update_ui():
            try:
                if self.text_area.text == new_text:
                    return
            except AttributeError:
                return

            self.suppress_local_event = True
            cursor = self.text_area.cursor_location

            self.text_area.text = new_text
            self.text_area.cursor_location = cursor

            self.suppress_local_event = False
            self.text = new_text

        # Use Textual's thread-safe scheduler
        self.app.call_from_thread(update_ui)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "notepad_export":
            try:
                save_path = os.path.join(SAVE_DIR, "notepad")
                os.makedirs(save_path, exist_ok=True)

                base = "notepad"
                ext = ".txt"
                filename = base + ext
                full = os.path.join(save_path, filename)

                # If the file exists, increment: notepad(1).txt, notepad(2).txt, ...
                counter = 1
                while os.path.exists(full):
                    filename = f"{base}({counter}){ext}"
                    full = os.path.join(save_path, filename)
                    counter += 1

                with open(full, "w", encoding="utf-8") as f:
                    f.write(self.text_area.text)

                self.notify(f"{full}", title="Notepad exported")
            except Exception as e:
                self.notify(f"{e}", title="Error exporting notepad!", severity="error")

    def reconnect(self):
        self.notify(f"Host changed, please press any key to resync...", title="Notepad", severity="warning")
        self.host.set_text(self.text_area.text)
        return
        #self.client.stop()
        #self.host.stop()
        #self.client = NotepadClient(
        #    on_update_callback=self.on_text_update_from_host
        #)
        #self.host = NotepadHost()
