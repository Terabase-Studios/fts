from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Placeholder
from pathlib import Path

from fts.app.backend.contacts import start_discovery_responder
from fts.app.frontend.contacts import Contacts
from fts.app.frontend.transfers import Transfer

def get_css_files():
    module_dir = Path(__file__).parent

    # Only pick .tcss files, ignore __pycache__
    css_files = [
        str(p.relative_to(module_dir))
        for p in module_dir.rglob("*.tcss")
        if "__pycache__" not in p.parts
    ]
    return css_files


def setup():
    start_discovery_responder()


class FTSApp(App):

    setup()

    CSS_PATH = get_css_files() + ["main.tcss"]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with Vertical():
            with Horizontal(id="toprow"):
                yield Contacts(id="toprowa")
                yield Placeholder(id="toprowb")
                yield Placeholder(id="toprowc")

            with Horizontal(id="bottomrow"):
                yield Placeholder(id="bottomrowa")
                yield Transfer(id="bottomrowb")


if __name__ == "__main__":
    FTSApp().run()