import sys

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Vertical, Horizontal
from textual.widgets import Collapsible, Label, Input, Button, Checkbox, Placeholder, SelectionList
from textual.widgets.selection_list import Selection
from textual import on

import tkinter as tk
from tkinter import filedialog
import tempfile
import zlib
import base64
import asyncio
from typing import Dict, Iterable
import time

from pathlib import Path

from fts.app.backend.contacts import ONLINE_USERS, replace_with_ip


class FileSelector(Horizontal):
    def __init__(self, **kargs):
        super().__init__(**kargs)
        self.path = None

    """An input that accepts pasted or dragged file paths."""
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Drag a file here or click Browse...", id="file_input")
        yield Button("Browse", id="browse_button", variant="primary")

    @on(Input.Changed, "#file_input")
    def handle_path_input(self, event: Input.Changed) -> None:
        """Handle pasted or dragged paths."""
        text = f"{event.value.strip().strip('"')}"
        try:
            self.path = Path(text)
        except ValueError:
            pass

    @on(Button.Pressed, "#browse_button")
    def handle_browse(self) -> None:
        ICON = zlib.decompress(base64.b64decode('eJxjYGAEQgEBBiDJwZDBy'
                                                'sAgxsDAoAHEQCEGBQaIOAg4sDIgACMUj4JRMApGwQgF/ykEAFXxQRc='))
        _, ICON_PATH = tempfile.mkstemp()
        with open(ICON_PATH, 'wb') as icon_file:
            icon_file.write(ICON)

        root = tk.Tk()
        root.iconbitmap(default=ICON_PATH)
        root.withdraw()
        root.wm_attributes("-topmost", True)
        real_path = filedialog.askopenfilename(initialfile=self.path, initialdir=self.path, title="", )
        root.destroy()
        if real_path == "":
            real_path = None

        try:
            input = self.get_widget_by_id("file_input")
            if Path(real_path).is_file():
                self.path = Path(real_path)
                input.value = f"{self.path}"
        except:
            pass


class ContactSelector(Container):
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="contact_scroll"):
            self.selection_list = SelectionList(id="contact_selection_list")
            yield self.selection_list

    async def on_mount(self):
        # Internal mapping: contact_value -> option_id (string)
        # We keep it on the instance so we can diff efficiently.
        self._contact_to_option_id: Dict[str, str] = {}

        if self.selection_list:
            # Do one immediate load
            asyncio.create_task(load_contacts(self.selection_list, self._contact_to_option_id, first_run=True))

            # Repeated updates every second
            async def update_loop():
                while True:
                    await asyncio.sleep(1)
                    await load_contacts(self.selection_list, self._contact_to_option_id)

            asyncio.create_task(update_loop())

    def select_all(self):
        """Select all contacts in the list."""
        if self.selection_list:
            self.selection_list.select_all()

    def deselect_all(self):
        """Deselect all contacts in the list."""
        if self.selection_list:
            self.selection_list.deselect_all()

    def get_selected(self) -> list[str]:
        """Return a list of contact names that are currently selected."""
        if not self.selection_list:
            return []

        # Only include the value of selections that are currently selected
        return self.selection_list.selected


async def load_contacts(selection_list: SelectionList, contact_map: Dict[str, str], first_run: bool = False):
    """
    Fetch updated contact list and diff it against current options.

    - Uses asyncio.to_thread to run blocking fetch in a thread.
    - Maintains contact_map: contact_value -> option_id.
    - Adds new Selection(...) with explicit id and removes by id with remove_option().
    """
    # Fetch in a non-blocking way (wrap blocking call in to_thread)
    new_contacts = ONLINE_USERS.get_online()
    new_set = set(new_contacts)
    existing_set = set(contact_map.keys())

    # Remove contacts that no longer exist
    to_remove = existing_set - new_set
    for contact in to_remove:
        option_id = contact_map.pop(contact, None)
        if option_id is not None:
            # Use remove_option(option_id) to remove a specific option by id.
            # This is the correct API (don't try to mutate .options directly).
            try:
                selection_list.remove_option(option_id)
            except Exception:
                # If removal fails for any reason, ignore and continue (could be OptionDoesNotExist)
                pass

    # Add new contacts (at end). We create Selection objects so we can give them stable IDs.
    for contact in new_contacts:
        if contact not in contact_map:
            # Make a safe id (ids must be unique). Avoid spaces or odd chars.
            option_id = f"contact-{contact}"
            # Selection(prompt, value, initial_state=False, id=None, disabled=False)
            sel = Selection(prompt=contact, value=contact, initial_state=False, id=option_id)
            try:
                selection_list.add_option(sel)
                contact_map[contact] = option_id
            except Exception:                pass

    # If list became empty, show a placeholder item
    if not new_contacts and (existing_set or first_run):
        selection_list.clear_options()


class Sending(Container):
    def compose(self) -> ComposeResult:
        with Vertical():
            self.file_selector = FileSelector()  # keep a reference
            yield self.file_selector

            self.contact_selector = ContactSelector()  # keep a reference
            yield self.contact_selector

            with Horizontal(id="sending_button_bar"):
                yield Button("Select All", id="select_all_button", variant="success")
                yield Button("Deselect All", id="deselect_all_button", variant="error")
                yield Button("Send", id="file_send_button", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        # make sure we can access the SelectionList inside ContactSelector
        contact_selector =  self.contact_selector
        file_selector =  self.file_selector


        if not contact_selector:
            return

        if button_id == "select_all_button":
            contact_selector.select_all()

        elif button_id == "deselect_all_button":
            contact_selector.deselect_all()

        elif button_id == "file_send_button":
            contacts = replace_with_ip(contact_selector.get_selected())
            file_path = file_selector.path

            if not contacts or not file_path or len(contacts) < 1:
                return

            # todo: Insert backend here
