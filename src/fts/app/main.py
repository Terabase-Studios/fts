import asyncio
import ctypes
import sys

from filelock import FileLock, Timeout
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import TabbedContent, Placeholder

from fts.cli import ICON
import fts.app.backend.transfer as transfer
import fts.py as fts
from fts import __version__
from fts.app.backend.contacts import start_discovery_responder
from fts.app.backend.host import host_manager, host_watcher
from fts.app.backend.library.network import start_library_responder
from fts.app.backend.plugins.importer import load_plugins
from fts.app.backend.transfer import TransferHandler
from fts.app.config import LOCK_FILE, LOG_FILE, EXPERIMENTAL_FEATURES_ENABLED
from fts.app.frontend.chat import Chat
from fts.app.frontend.contacts import Contacts
from fts.app.frontend.library import LibraryView
from fts.app.frontend.notepad import NotepadWindow
from fts.app.frontend.requests import Requests
from fts.app.frontend.sending import Sending
from fts.app.frontend.transfers import Transfers
from fts.app.style.tcss import css

fts_app = None

def setup(transfer_ui: Transfers, requests_ui: Requests) -> None:
    fts.logger = LOG_FILE
    start_discovery_responder()
    start_library_responder()
    transfer.transfer_handler = TransferHandler(transfer_ui, requests_ui)
    host_manager.start()
    host_watcher.start()

class FTSApp(App):

    #CSS_PATH = [
    #    "style\\main.tcss",
    #    "style\\contacts.tcss",
    #    "style\\transfers.tcss",
    #    "style\\chat.tcss",
    #    "style\\sending.tcss",
    #    "style\\requests.tcss",
    #    "style\\library.tcss",
    #    "style\\notepad.tcss",
    #]

    CSS = css

    def compose(self=None) -> ComposeResult:
        #yield Header()
        #yield Footer()

        stable = ["Main", "Library"]
        experimental = ["Notepad"]
        if EXPERIMENTAL_FEATURES_ENABLED:
            tabs = stable + experimental
        else:
            tabs = stable

        with TabbedContent(*tabs):
            with Vertical():
                with Horizontal(id="toprow"):
                    yield Contacts(id="toprowa")
                    yield Sending(id="toprowb")
                    requests = Requests(id="toprowc")
                    yield requests

                with Horizontal(id="bottomrow"):
                    yield Chat(id="bottomrowa")
                    transfers = Transfers(id="bottomrowb")
                    yield transfers
            yield LibraryView()

            if EXPERIMENTAL_FEATURES_ENABLED:
                notepad = NotepadWindow(id="notepad")
                host_manager.host_changed_funcs.append(notepad.reconnect)
                yield notepad


        setup(transfer_ui=transfers, requests_ui=requests)

    async def action_quit(self) -> None:
        transfer.transfer_handler.cancel_all()
        await asyncio.sleep(.01)
        await super().action_quit()

    def on_mount(self) -> None:
        pass


def start(print_icon = False):
    global fts_app
    if print_icon:
        print(ICON)

    if sys.platform == "win32":  # Check if running on Windows
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except AttributeError:
            # Handle cases where SetProcessDpiAwareness might not be available
            pass

    lock = FileLock(LOCK_FILE)

    try:
        # Try to acquire the lock for 1 second
        with ((lock.acquire(timeout=1))):
            try:
                load_plugins()
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[PLUGIN IMPORTER ERROR] Failed to load plugins: {e}")
            fts_app = FTSApp()
            fts_app.run()
    except Timeout:
        print("Another instance of the FTS App is already running! Only one instance is allowed at a time.")

    print('')