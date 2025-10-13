from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Vertical, Horizontal
from textual.widgets import Collapsible, Label, Input, Button, Checkbox, Placeholder
from textual import on

from pathlib import Path

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
        text = f"[cyan]{event.value.strip().strip('"')}[/]"
        try:
            self.path = Path(text)
        except ValueError:
            pass

    @on(Button.Pressed, "#browse_button")
    def handle_browse(self) -> None:
        pass

class Sending(Container):
    def compose(self) -> ComposeResult:
        with Vertical():
            yield FileSelector()

            with VerticalScroll():
                with Horizontal():
                    yield Placeholder()
                    yield Placeholder()

            with Horizontal():
                yield Placeholder()
                yield Placeholder()
                yield Placeholder()
