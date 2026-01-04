import sys

from textual.widgets import Tree, Input, Switch
from textual.widgets.tree import TreeNode
from textual.events import Key
from fts.app.backend.library import FTSLibrary, LIBRARY_PATH
from fts.app.backend.library.network import FTSNetLibrary, get_libraries, ask_for_file

import socket
import datetime

from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Vertical, Horizontal
from textual.widgets import Label, Button, Rule, Log, Collapsible

from fts.app.backend.contacts import ONLINE_USERS, replace_with_ip, replace_with_contact
from fts.app.config import logger, library_enabled, set_config_value
import fts.app.config as app_config

RED = "\033[31m"
RESET = "\033[0m"
LIBRARY_HELP = f'''
    The library is a place where you can request files from others without them having to find and send the file to you themselves.

    When you press enter on a selected file, or just click a file, you should see a request popup in the "Main" menu to send you the file!

    If you don't see the transfer request, wait ~30 seconds. The library may get overwhelmed with many file requests. 
    
    If there is still no transfer request, then refresh this page and try the transfer again if the file is available.

Your library directory: {LIBRARY_PATH}
'''


class LibraryView(Container):
    def compose(self) -> ComposeResult:
        with Horizontal() as h:
            self.horizontal = h
            self.library = LibraryTreeDisplay()
            self.panel = LibraryPanel(self)
            yield self.library
            yield self.panel

    def refresh_self(self):
        self.library.remove()
        self.panel.remove()
        self.library = LibraryTreeDisplay()
        self.panel = LibraryPanel(self)
        self.horizontal.mount(self.library)
        self.horizontal.mount(self.panel)


class LibraryPanel(Vertical):
    def __init__(self, library_view: LibraryView, **kwargs):
        super().__init__(**kwargs)
        self.library_view = library_view\

    def compose(self) -> ComposeResult:
        with Vertical() as h:
            yield Label(f"Library open:", id="library_switch_text")
            yield Switch(value=app_config.library_enabled, id="library_switch")
            h.styles.height = "auto"

        yield Label(LIBRARY_HELP, id="library_help_text")

        yield Button("Refresh", variant="primary", id="library_refresh")
        date = datetime.datetime.now()

        if len(str(date.minute)) == 1:
            minute = f"0{date.minute}"
        else:
            minute = f"{date.minute}"

        if len(str(date.second)) == 1:
            seconds = f"0{date.second}"
        else:
            seconds = f"{date.second}"
        yield Label(f"Last refresh: {date.hour}:{minute}:{seconds}")


    def on_switch_changed(self, event: Switch.Changed):
        if event.switch.id == "library_switch":
            set_config_value("LIBRARY_ENABLED", str(event.value).lower())
            app_config.library_enabled = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "library_refresh":
            self.refresh_tree_view()

    def refresh_tree_view(self):
        self.library_view.refresh_self()


def get_ip():
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    return local_ip


class LibraryTreeDisplay(Vertical):
    """
    Displays local and remote libraries.
    Local library is added in compose.
    Remote libraries are added on_mount dynamically.
    """

    def compose(self) -> ComposeResult:
        self.library_widgets: dict[str, LibraryTree] = {}
        self.remote_libraries: dict[str, FTSNetLibrary] = {}

        self_ip = get_ip()
        self.local_lib = FTSLibrary()
        self.local_tree_widget = LibraryTree(self.local_lib)
        self.library_widgets["self"] = self.local_tree_widget

        yield VerticalScroll(id="tree_scroll")


        yield Input(placeholder="Search Libraries", id="library_search")

    def on_input_changed(self, event: Input.Changed) -> None:
        value = event.value
        for widget in self.library_widgets.values():
            widget.search(value)

    async def on_mount(self) -> None:
        for user, tree in await get_libraries():
            # Create remote library placeholder
            net_lib = FTSNetLibrary(user, tree)
            self.remote_libraries[user] = net_lib
            tree_widget = LibraryTree(library=net_lib)
            self.library_widgets[user] = tree_widget

            # Add collapsible dynamically
            scroll = self.get_widget_by_id("tree_scroll")
            collapsible = Collapsible(title=f"{replace_with_contact(user)}'s Library", classes="TreeTab")
            collapsible.compose_add_child(tree_widget)

            await scroll.mount(collapsible)


class LibraryTree(Tree):
    """A Tree widget showing folders and files with sizes, supports local or network libraries."""

    def __init__(self, library: FTSLibrary | FTSNetLibrary = FTSLibrary() , name: str | None = None):
        """
        `library` can be an instance of FTSLibrary or FTSNetLibrary.
        """
        self.library = library
        self.ip = get_ip() if type(library) is FTSLibrary else self.library.ip
        super().__init__(label="Library", name=name)
        self._build_tree()

    def on_mount(self):
        self._last_selected = None

    def _build_tree(self):
        """Populate the tree widget from the library tree."""
        self.root.label = "Library"
        self.root.data = {"type": "folder"}
        self.clear()
        self._add_nodes(self.root, self.library.tree)
        self.root.expand()

    def _add_nodes(self, node: TreeNode, tree_data: dict):
        """Recursively add folders and files to the TreeNode, directories first."""
        dirs = [k for k in tree_data.keys() if k != "files"]
        files = tree_data.get("files", [])

        # Add directories first
        for key in sorted(dirs):
            child_node = node.add(f"{key}/", data={"type": "folder"})
            self._add_nodes(child_node, tree_data[key])

        # Then add files
        for f in sorted(files, key=lambda x: x["name"].lower()):
            size_str = self._format_size(f.get("size", 0))
            node.add_leaf(f"{f['name']} ([bold red]{size_str}[white])",
                          data={"type": "file", "id": f["id"]})

    def refresh_library(self):
        """Refresh the library and rebuild the tree if updated."""
        if self.library.update():  # works for FTSNetLibrary too
            self._build_tree()

    @staticmethod
    def _format_size(size: int) -> str:
        """Convert bytes to human-readable format."""
        for unit in ['B','KB','MB','GB','TB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}PB"

    def search(self, phrase: str):
        phrase = phrase.strip()
        self._current_search_phrase = phrase  # <- store for highlight use

        if not phrase:
            self._build_tree()
            return

        results = set(self.library.search(phrase))

        self.clear()
        self._add_filtered(self.root, self.library.tree, results)
        self.root.expand_all()

    def _add_filtered(self, node: TreeNode, tree_data: dict, results: set[str]) -> bool:
        """
        Returns True if this branch contains any match.
        Adds only matching leaves or folders containing them.
        """
        found_any = False

        # Check subdirectories first
        for dirname, subtree in tree_data.items():
            if dirname == "files":
                continue
            # make folder node *only if* something under it matches
            child = node.add(f"{dirname}/", data={"type": "folder"})
            has_match = self._add_filtered(child, subtree, results)
            if not has_match:
                child.remove()  # prune branch
            else:
                found_any = True

        # Check files
        for f in tree_data.get("files", []):
            file_id = f["id"]
            if file_id in results:
                size_str = self._format_size(f.get("size", 0))

                # highlight name
                highlighted_name = self._highlight(f["name"], self._current_search_phrase)

                node.add_leaf(
                    f"{highlighted_name} ([bold red]{size_str}[white])",
                    data={"type": "file", "id": file_id},
                )
                found_any = True

        return found_any

    def _highlight(self, text: str, phrase: str) -> str:
        """Highlight the matching part of the text."""
        lower = text.lower()
        phrase_lower = phrase.lower()

        idx = lower.find(phrase_lower)
        if idx == -1:
            return text  # no match

        end = idx + len(phrase)
        return (
                text[:idx] +
                f"[yellow]{text[idx:end]}[/yellow]" +
                text[end:]
        )

    async  def on_tree_node_selected(self, event: Tree.NodeSelected):
        node = event.node
        self._last_selected = node

        if event:
            await self._activate_node(node)

    async def on_key(self, event: Key):
        if event.key != "enter":
            return

        node = self._last_selected
        if not node:
            return

        await self._activate_node(node)

    async def _activate_node(self, node: TreeNode):
        data = node.data or {}
        if data.get("type") == "file":

            file_id = data["id"]
            if file_id is not None:
                await self.on_file_activated(file_id)

    async def on_file_activated(self, file_id: str):
        success = await ask_for_file(self.ip, file_id)
        if success:
            self.notify(f"Sent library request to {replace_with_contact(self.ip)}: {file_id}")
            logger.info(f"[Library][Frontend] Sent library request to {replace_with_contact(self.ip)}: {file_id}")
        else:
            self.notify(f"Failed to send library request to {replace_with_contact(self.ip)}: {file_id}", severity="error")
            logger.error(f"[Library][Frontend] Failed to send library request to {replace_with_contact(self.ip)}: {file_id}")