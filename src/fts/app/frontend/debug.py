import os
import sys
import re


from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Button, ListView, Select, RichLog, ListItem, Label
from textual.widgets import TextArea

from fts.app.backend.debug import parse_log, colorize_log_line, filter_logs


class DebugView(Container):

    def __init__(self):
        super().__init__()
        self.data, self.metadata = parse_log()
        self.selected_instance = None
        if self.metadata:
            self.selected_instance = list(self.metadata.keys())[-1]

    def compose(self) -> ComposeResult:
        print(self.data)
        with Horizontal():
            items = [ListItem(Label(f"({i})-[{str(self.data[i][0])[11:]}>{str(self.data[i][1])[11:]}]")) for i in self.data]
            items.reverse()
            yield ListView(
                *items,
                id="InstanceSelector"
            )
            yield Reader(self.metadata[self.selected_instance], self.data[self.selected_instance])



class Reader(Vertical):
    def __init__(self, metadata, data):
        super().__init__()
        self.data = data
        self.metadata = metadata

    def compose(self) -> ComposeResult:
        with Horizontal(id="LogSelectorBar"):
            severity_options = [("---", "---")]+[(line, line) for line in self.metadata["severity"]]
            module_options = [("---", "---")]+[(line, line) for line in self.metadata["modules"]]
            yield LogFilterSelector(severity_options, allow_blank=False, id="severity_select")
            yield LogFilterSelector(module_options, allow_blank=False)
            yield LogFilterSelector([("---", "---")], allow_blank=False)
        lines = []
        for i in range(len(self.data[2])):
            line = self.data[2][i]["raw"]
            lines.append(colorize_log_line(line))
        yield DebugLog(lines)


class DebugLog(RichLog):
    def __init__(self, debug_lines):
        super().__init__()
        self.log_lines = debug_lines

    def _on_mount(self) -> None:
        super()._on_mount(self)
        for line in self.log_lines:
            self.write(line)


class LogFilterSelector(Select):
    pass




if __name__ == "__main__":
    data, metadata = parse_log()
    print((data, metadata))
    instance = list(metadata.keys())[-1]
    print(data[instance][2][0])
