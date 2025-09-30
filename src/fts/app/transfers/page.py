from docutils.nodes import entry
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, HorizontalGroup, Container
from textual.widgets import Footer, Header, Collapsible, Label
from fts.app.transfers.history import parse_transfers

class LogEntry(Container):
    def __init__(self, entry):
        super().__init__()
        self.entry = entry
        if self.entry["status"] == "success":
            self.add_class("success")
        elif self.entry["status"] == "error":
            self.add_class("error")

    def compose(self) -> ComposeResult:
        print(self.entry)
        entry = self.entry
        heading = f"{entry['start_time']}> {entry['type']}, {entry['file']}"
        with Collapsible(title=heading, id="logtab"):
            yield Label("This is a log entry")

class transferpage(App):
    def __init__(self, history):
        super().__init__()
        self.history = history

    CSS_PATH = "transfer.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        # Active section
        with Collapsible(title="Active", collapsed=False):
            yield Label("Current transfers will show up here")

        # History section
        with Collapsible(title="History", collapsed=False):
            if not self.history:
                yield Label("Past transfers will show up here")
            else:
                with VerticalScroll():
                    for entry in self.history:
                        yield LogEntry(entry)

# Example usage:
if __name__ == "__main__":
    log_text = open("C:\\Users\\cybor\\Downloads\\log.txt").read()
    history = parse_transfers(log_text)
    #for line in history[0]:
    #    print(f"{line}: {history[0][line]}")
    app = transferpage(history)
    app.run()