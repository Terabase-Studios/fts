import os
import random
import sys
import re
from configparser import ConfigParser

from rich.align import VerticalCenter
from sympy import false
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll, Grid, ItemGrid, HorizontalScroll, Middle
from textual.getters import query_one
from textual.screen import ModalScreen
from textual.selection import Selection
from textual.widgets import Button, ListView, Select, RichLog, ListItem, Label, TabbedContent, Placeholder, Rule, \
    Switch, Input
from textual.widgets import TextArea

from fts.config import resave_config as reset_main_config
from fts.app.config import resave_config as reset_app_config
from fts.config import CONFIG_FILE as MAIN_CONFIG
from fts.app.config import CONFIG_PATH as APP_CONFIG
from fts.app.backend.debug import parse_log, colorize_log_line, filter_logs
from fts.app.config import DEBUG_FILE, SAVE_DIR, EXPERIMENTAL_FEATURES_ENABLED, APP_DIR

EXCLUDED_SECTIONS = ["paths", "compression", "core"]
EXCLUDED_SETTINGS = ["config_version", "library_enabled"]

def is_float(value):
  """
  Checks if a string is a valid float using a try-except block.
  """
  try:
    float(value)
    return True
  except ValueError:
    return False

class SettingsView(Container):

    def __init__(self):
        super().__init__()
        self.parsers = []


    def compose(self) -> ComposeResult:
        with TabbedContent(*["Base", "App"], id="SettingsFileSelector"):
            yield ConfigReader(MAIN_CONFIG)
            yield ConfigReader(APP_CONFIG)


class ConfigReader(HorizontalScroll):
    def __init__(self, config_path, *args):
        super().__init__(*args)
        self.config_path = config_path
        self.parser = None
        self.unchanged_parser = None
        self.changed_parser = False

    def compose(self) -> ComposeResult:
        with Middle(id="ConfigButtons"):
            yield Spacer()
            yield Button("Save", id="ConfigSave", variant="success", disabled=True)
            yield Spacer()
            yield Button("Reset", id="ConfigReset", variant="warning", disabled=True)
            yield Spacer()
            yield Button("Delete", id="ConfigDelete", variant="error")
            yield Spacer()

        base_parser = ConfigParser()
        base_parser.read(self.config_path)
        self.unchanged_parser = ConfigParser()
        self.unchanged_parser.read(self.config_path)
        self.parser = base_parser
        for section in base_parser.sections():
            if section.lower() in EXCLUDED_SECTIONS:
                continue
            with Section() as container:
                container.border_title = section
                for item in base_parser.items(section):
                    if item[0] in EXCLUDED_SETTINGS:
                        continue
                    with Item():
                        id = f"LOC{section}-{item[0]}"
                        yield ConfigText(item[0])
                        if section.lower() == "plugins":
                            yield BoolInput(value=base_parser[section].getboolean(item[0]), id = id)
                        elif item[0].endswith("_enabled"):
                            yield BoolInput(value=base_parser[section].getboolean(item[0]), id = id)
                        elif item[1].isdigit():
                            yield NumericInput(value=item[1], type="integer", id = id)
                        elif is_float(item[1]):
                            yield NumericInput(value=item[1], type="number", id = id)
                        else:
                            yield NumericInput(value=item[1], type="text", id = id)

    def on_input_changed(self, event: Input.Changed):
        if not event.validation_result:
            return
        self.update_config_value(event.input.id, event.value)

    def on_switch_changed(self, event: Switch.Changed):
        self.update_config_value(event.switch.id, "true" if event.value else "false")

    def update_config_value(self, id, value):
        location = id.removeprefix("LOC").split("-")
        self.parser[location[0]][location[1]] = value

        self.changed_parser = self.parser == self.unchanged_parser
        button = self.get_widget_by_id("ConfigSave")
        button.disabled = self.changed_parser
        button = self.get_widget_by_id("ConfigReset")
        button.disabled = self.changed_parser

    def on_button_pressed(self, event: Button.Pressed):
        divided_config_end_path = os.path.dirname(self.config_path).replace("\\", "/").split("/")[-1]
        config_info = divided_config_end_path + "/" + os.path.basename(self.config_path)
        if event.button.id == "ConfigSave":
            try:
                pass
                with open(self.config_path, "w") as f:
                    self.parser.write(f)
            except Exception as e:
                self.notify(f"{config_info} failed to override", title="Configuration Error", severity="error")
            else:
                self.unchanged_parser = ConfigParser()
                self.unchanged_parser.read(self.config_path)
                self.changed_parser = False
                event.button.disabled = True
                button = self.get_widget_by_id("ConfigReset")
                button.disabled = True
                self.notify(f"{config_info} overridden", title="Configuration Saved")
                self.notify(f"Configuration changes require a restart to take effect", title="Configuration Notice", severity="warning")

        elif event.button.id == "ConfigReset":
            self.notify(f"Reverting unsaved changes to {config_info}", title="Configuration Reverted", severity="warning")
            self.parent.mount(ConfigReader(self.config_path))
            self.remove()

        elif event.button.id == "ConfigDelete":
            self.app.push_screen(ConfirmDelete(), self.handle_delete)

    def handle_delete(self, result: bool):
        if result:
            divided_config_end_path = os.path.dirname(self.config_path).replace("\\", "/").split("/")[-1]
            config_info = divided_config_end_path + "/" + os.path.basename(self.config_path)

            if self.config_path == MAIN_CONFIG:
                reset_main_config()
            elif self.config_path == APP_CONFIG:
                reset_app_config()
            else:
                self.notify(f"{config_info} failed to delete; Unrecognized config path", title="Configuration Error", severity="error")

            self.notify(f"{config_info} deleted; Backup created", title="Configuration Deleted")
            self.notify(f"Configuration changes require a restart to take effect", title="Configuration Notice", severity="warning")
            self.parent.mount(ConfigReader(self.config_path))
            self.remove()


class ConfirmDelete(ModalScreen[bool]):
    def compose(self) -> ComposeResult:
        with Middle(id="ConfirmDeleteContainer"):
            yield CenterText("This will allow FTS to regenerate a fresh version of this config file.")
            yield CenterText("A backup will be created. Confirm Delete?")
            yield Spacer()
            with Horizontal(id="ConfirmDeleteButtonBar"):
                yield Button("delete", variant="primary", id="ConfirmDelete")
                yield Button("cancel", variant="success", id="CancelDelete")
            yield Spacer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ConfirmDelete":
            self.dismiss(True)

        elif event.button.id == "CancelDelete":
            self.dismiss(False)



class Spacer(Container):
    pass

class Section(VerticalScroll):
    pass

class Item(Vertical):
    pass

class NumericInput(Input):
    pass

class BoolInput(Switch):
    pass

class ConfigText(Label):
    pass

class CenterText(Label):
    pass