from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Placeholder

from fts.app.backend.contacts import start_discovery_responder
from fts.app.frontend.contacts import Contacts
from fts.app.frontend.transfers import Transfer
from fts.app.frontend.chat import Chat

from fts.app.style.tcss import css

def setup():
    start_discovery_responder()


class FTSApp(App):

    setup()

    CSS_PATH = [
        "style\\main.tcss",
        "style\\contacts.tcss",
        "style\\transfers.tcss",
        "style\\chat.tcss"
    ]

    #CSS = css

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with Vertical():
            with Horizontal(id="toprow"):
                yield Contacts(id="toprowa")
                yield Placeholder(id="toprowb")
                yield Placeholder(id="toprowc")

            with Horizontal(id="bottomrow"):
                yield Chat(id="bottomrowa")
                yield Transfer(id="bottomrowb")


def start():
    FTSApp().run()