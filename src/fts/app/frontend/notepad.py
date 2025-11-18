import sys
import os

from textual.widgets import Tree, Input, Switch, Placeholder, TextArea
from textual.widgets.tree import TreeNode
from textual.events import Key
from fts.app.backend.library import FTSLibrary, LIBRARY_PATH
from fts.app.backend.library.network import FTSNetLibrary, get_libraries, ask_for_file

import socket
import datetime

from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Vertical, Horizontal
from textual.widgets import Label, Button, Rule, Log, Collapsible

from fts.app.backend.contacts import ONLINE_USERS, replace_with_ip, replace_with_contact
from fts.app.config import logger, library_enabled, set_config_value, SAVE_DIR
import fts.app.config as app_config

from pycrdt import Doc


class NotepadWindow(Container):
    def compose(self) -> ComposeResult:
        self.text_area = TextArea(id="notepad")
        yield self.text_area
        yield Button("Export", id="notepad_export", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "notepad_export":
            try:
                save_path = os.path.join(os.path.join(SAVE_DIR, "fts"), "notepad")
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