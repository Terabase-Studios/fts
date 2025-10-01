from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Placeholder
from fts.app.transfers.widget import Transfer


class FTSApp(App):
    CSS_PATH = ["main.tcss", "transfers\\transfer.tcss"]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

        with Vertical():
            with Horizontal(id="toprow"):
                yield Placeholder(id="toprowa")
                yield Placeholder(id="toprowb")
                yield Placeholder(id="toprowc")

            with Horizontal(id="bottomrow"):
                yield Placeholder(id="bottomrowa")
                yield Transfer(id="bottomrowb")


if __name__ == "__main__":
    FTSApp().run()