import os
import random
import sys
import re
from configparser import ConfigParser

from sympy import false
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.getters import query_one
from textual.widgets import Button, ListView, Select, RichLog, ListItem, Label, TabbedContent, Placeholder, Rule, \
    Switch, Input
from textual.widgets import TextArea

from fts.config import CONFIG_FILE
from fts.app.backend.debug import parse_log, colorize_log_line, filter_logs
from fts.app.config import DEBUG_FILE, SAVE_DIR, EXPERIMENTAL_FEATURES_ENABLED

EXCLUDED_SECTIONS = ["paths", "compression"]
EXCLUDED_SETTINGS = ["config_version"]

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


    def compose(self) -> ComposeResult:
        with TabbedContent(*["Base", "App", "Library", "Plugins"], id="SettingsFileSelector"):
            with Vertical():
                base_parser = ConfigParser()
                base_parser.read(CONFIG_FILE)
                for section in base_parser.sections():
                    if section in EXCLUDED_SECTIONS:
                        continue
                    with Section() as container:
                        container.border_title = section
                        for item in base_parser.items(section):
                            if item[0] in EXCLUDED_SETTINGS:
                                continue
                            yield Label(item[0])
                            if item[0].endswith("_enabled"):
                                yield Switch(value=base_parser[section].getboolean(item[0]))
                            elif item[1].isdigit():
                                yield Input(value=item[1], type="integer")
                            elif is_float(item[1]):
                                yield Input(value=item[1], type="number")


            yield Placeholder()
            yield Placeholder()
            yield Placeholder()


class Section(Vertical):
    pass


if __name__ == "__main__":
    configparser = ConfigParser()
    configparser.read(CONFIG_FILE)
    for section in configparser.sections():
        print(section)
        for item in configparser.items(section):
            if item[0] == "config_version":
                continue
            #print(item)
