import os
import random
import sys
import re

from sympy import false
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.getters import query_one
from textual.widgets import Button, ListView, Select, RichLog, ListItem, Label
from textual.widgets import TextArea

from fts.app.backend.debug import parse_log, colorize_log_line, filter_logs
from fts.app.config import DEBUG_FILE, SAVE_DIR


class DebugView(Container):

    def __init__(self):
        super().__init__()
        self.data, self.metadata = parse_log()
        self.selected_instance = None
        self.no_log = False
        if self.metadata:
            self.selected_instance = list(self.metadata.keys())[-1]
        else:
            self.no_log = True
        self.reader = None
        self.horizontal_container = Horizontal()

    def compose(self) -> ComposeResult:
        with self.horizontal_container:
            if self.no_log:
                label = Label(" No logs found! Only previous sessions show here!")
                yield label
                return

            with Vertical():
                items = [ListItem(Label(f"({i})-[{str(self.data[i][0])[11:]}>{str(self.data[i][1])[11:]}]")) for i in self.data]
                items.reverse()
                yield ListView(
                    *items,
                    id="InstanceSelector"
                )
                yield Button("Export", variant="primary", id="LogExportButton")
            self.reader = Reader(self.metadata[self.selected_instance], self.data[self.selected_instance])
            yield self.reader

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "LogExportButton":
            with open(DEBUG_FILE, "r") as read:
                try:
                    filename = f"debug{random.randint(1111, 9999)}.txt"
                    filepath = os.path.join(SAVE_DIR, os.path.join("exported_debug_files", filename))
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, "w") as write:
                        write.write(read.read())
                except Exception as e:
                    self.notify(f"Failed to create logfile: {e} Please try again", title="Failed to export Debug.txt", severity="error")
                else:
                    self.notify(f"Exported as {filename}", title="Exported Debug.txt")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "InstanceSelector":
            return

        index = event.list_view.index
        if index is None:
            return

        # Because you reversed the list
        real_index = len(self.data) - 1 - index

        self.selected_instance = list(self.metadata.keys())[real_index]

        # Recreate Reader with new instance
        current_severity = self.reader.current_severity
        current_module = self.reader.current_module
        current_submodule = self.reader.current_submodule

        self.reader.remove()
        self.reader = Reader(
            self.metadata[self.selected_instance],
            self.data[self.selected_instance],
            current_severity,
            current_module,
            current_submodule
        )
        self.horizontal_container.mount(self.reader)


class Reader(Vertical):
    def __init__(self, metadata, data, current_severity="---", current_module="---", current_submodule="---"):
        super().__init__()
        self.data = data
        self.metadata = metadata
        self.current_severity = current_severity
        self.current_module = current_module
        self.current_submodule = current_submodule
        self.starting_filter = [current_severity, current_module, current_submodule]
        self.severity_selection_widget = None
        self.module_selection_widget = None
        #self.submodule_selection_widget = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="LogSelectorBar"):
            severity_options = [("---", "---")]+[(line, line) for line in self.metadata["severity"]]
            module_options = [("---", "---")]+[(line, line) for line in self.metadata["modules"]]
            if self.current_module and self.current_module != "---" and self.metadata["modules"].get(self.current_module):
                submodule_options = [("---", "---")]+[(line, line) for line in self.metadata["modules"][self.current_module]]
            else:
                submodule_options = [("---", "---")]
            self.severity_selection_widget = LogFilterSelector(severity_options, allow_blank=False, id="severity_select")
            self.module_selection_widget = LogFilterSelector(module_options, allow_blank=False, id="module_select")
            #self.submodule_selection_widget =  LogFilterSelector(submodule_options, allow_blank=False, id="submodule_select")

            severity_values = [v for _, v in severity_options]
            module_values = [v for _, v in module_options]
            submodule_values = [v for _, v in submodule_options]

            self.starting_filter[0] = self.current_severity if self.current_severity in severity_values else "---"
            self.starting_filter[1] = self.current_module if self.current_module in module_values else "---"
            #self.starting_filter[2] = self.current_submodule if self.current_submodule in submodule_values else "---"


            yield self.severity_selection_widget
            yield self.module_selection_widget
            #yield self.submodule_selection_widget

        lines = []
        for i in range(len(self.data[2])):
            line = self.data[2][i]["raw"]
            lines.append(colorize_log_line(line))
        yield DebugLog(lines)

    def _on_mount(self, event: events.Mount) -> None:
        super()._on_mount(event)
        self.severity_selection_widget.value = self.starting_filter[0]
        self.module_selection_widget.value = self.starting_filter[1]
        #self.submodule_selection_widget.value = self.starting_filter[2]

    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = event.select.id
        new_value = event.value

        if select_id == "severity_select":
            self.current_severity = new_value
        elif select_id == "module_select":
            self.current_module = new_value

            if self.current_module and self.current_module != "---" and self.metadata["modules"].get(self.current_module):
                submodule_options = [("---", "---")] + [(line, line) for line in self.metadata["modules"][self.current_module]]
                self.current_submodule = submodule_options[0][1]  # default to first submodule
            else:
                submodule_options = [("---", "---")]
                self.current_submodule = "---"

            #self.submodule_selection_widget.set_options(submodule_options)
            #self.submodule_selection_widget.value = self.current_submodule
        elif select_id == "submodule_select":
            self.current_submodule = new_value
        self.query_one(DebugLog).filter(self.current_severity, self.current_module, self.current_submodule)

class DebugLog(RichLog):
    def __init__(self, debug_lines):
        super().__init__()
        self.log_lines = debug_lines

    def _on_mount(self, event: events.Mount) -> None:
        super()._on_mount(event)
        for line in self.log_lines:
            self.write(line)

    def filter(self, severity: str, module: str, submodule: str) -> None:
        if severity == "---":
            severity = None
        if module == "---":
            module = None
        if submodule == "---":
            submodule = None
        self.clear()
        lines_written = False
        for line in filter_logs(self.log_lines, severity, module, submodule):
            lines_written = True
            self.write(colorize_log_line(line))
        if not lines_written:
            self.write("No lines match filters!")


class LogFilterSelector(Select):
    pass




if __name__ == "__main__":
    data, metadata = parse_log()
    print((data, metadata))
    instance = list(metadata.keys())[-1]
    print(data[instance][2][0])
