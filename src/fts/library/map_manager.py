from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from pathlib import Path
from fts.library.map import LibraryMap
from fts.library.tree import build_library_tree, VirtualLibrary
import tkinter as tk
from tkinter import filedialog
import os
import string


class MapManager:
    """
    Combines a LibraryMap with a virtual tree for navigation.
    Allows cd/ls in the tree, and add/remove/rename/save operations.
    """

    def __init__(self, lm: LibraryMap):
        self.lm = lm
        self.tree = build_library_tree(lm.map)
        self.vl = VirtualLibrary(self.tree)


class MapCompleter(Completer):
    def __init__(self, manager: MapManager):
        self.manager = manager
        self.commands = ["ls", "cd", "pwd", "tree", "add", "remove", "rename", "save", "exit"]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        parts = text.split()

        if not parts:
            for cmd in self.commands:
                yield Completion(cmd, start_position=0)
            return

        cmd = parts[0].lower()
        arg = text[len(parts[0]):].lstrip()

        # Command completion
        if len(parts) == 1 and not text.endswith(" "):
            for c in self.commands:
                if c.startswith(cmd):
                    yield Completion(c, start_position=-len(cmd))
            return

        # Virtual path completion for cd/remove/rename
        if cmd == "cd":
            base_node, last = self.resolve_path(arg, self.manager.vl.cwd)
            if base_node is None:
                return

            for name, value in base_node.items():
                if value and name.startswith(last):
                    completion_text = "/".join(arg.split("/")[:-1] + [name])
                    yield Completion(completion_text, start_position=-len(arg))

            # Suggest '..' if not at root
            if self.manager.vl.cwd != self.manager.vl.root:
                yield Completion("..", start_position=-len(last))

        if cmd in ("remove", "rename"):
            base_node, last = self.resolve_path(arg, self.manager.vl.cwd)
            if base_node is None:
                return

            # Recursive helper to collect all files under a node with their relative paths
            def collect_files(node, prefix=""):
                results = []
                for name, value in node.items():
                    path = f"{prefix}/{name}" if prefix else name
                    if value:  # Directory
                        results.extend(collect_files(value, path))
                    else:  # File
                        results.append(path)
                return results

            files = collect_files(base_node)
            # Filter by what the user has typed and sort by depth
            for f in sorted(files, key=lambda x: x.count("/")):
                if f.startswith(last):
                    # Prepend any path components before last in arg
                    completion_text = "/".join(arg.split("/")[:-1] + [f])
                    yield Completion(completion_text, start_position=-len(arg))

        # Real filesystem path completion for add
        if cmd == "add" and len(parts) >= 3:
            real_arg = parts[-1]

            # --- Handle Windows drives / root directories ---
            if not real_arg or (os.name == "nt" and len(real_arg) == 1 and real_arg.upper() in string.ascii_uppercase):
                if os.name == "nt":
                    # Suggest all available drives
                    drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
                    for d in drives:
                        yield Completion(d, start_position=-len(real_arg))
                else:
                    # Unix-like, start at root
                    yield Completion("/", start_position=-len(real_arg))

                yield Completion("gui", start_position=-len(real_arg))
                return

            # --- Continue normal path completion ---
            base = Path(real_arg)
            if base.exists() and base.is_dir():
                candidates = list(base.iterdir())
                prefix = base.as_posix() + "/"
                last = ""
            else:
                parent = base.parent if base.parent.exists() else None
                if parent:
                    candidates = list(parent.iterdir())
                    prefix = parent.as_posix() + "/"
                else:
                    candidates = []
                    prefix = ""
                last = base.name

            # Separate files and dirs
            file_cands = [c for c in candidates if c.is_file()]
            dir_cands = [c for c in candidates if c.is_dir()]

            # Yield files first
            for cand in file_cands:
                if cand.name.startswith(last):
                    yield Completion(prefix + cand.name, start_position=-len(real_arg))

            # Then dirs
            for cand in dir_cands:
                if cand.name.startswith(last):
                    yield Completion(prefix + cand.name + "/", start_position=-len(real_arg))

            yield Completion("gui", start_position=-len(real_arg))

    def resolve_path(self, path, start_node):
        """Helper to traverse virtual tree node by path string"""
        node = start_node
        components = path.split("/")
        for comp in components[:-1]:
            if comp == "..":
                node = self.manager.vl.get_parent(node)
            elif comp in node and node[comp]:
                node = node[comp]
            else:
                return None, components[-1]
        last = components[-1] if components else ""
        return node, last

def browse_map(lm: LibraryMap):
    manager = MapManager(lm)
    session = PromptSession()
    completer = MapCompleter(manager)

    print("Welcome to the Virtual Library Editor!")
    print("Commands: ls, cd <dir>, pwd, tree, add <name> <real_path>, remove <name>, rename <old> <new>, save, exit")
    print("Library structure:")
    manager.vl.tree()
    print('')

    while True:
        try:
            command = session.prompt(f"[{manager.vl.pwd()}] > ", completer=completer, complete_while_typing=True).strip()
        except KeyboardInterrupt:
            return
        except EOFError:
            print("\nExiting map manager.")
            return

        if not command:
            continue

        parts = command.split()
        cmd = parts[0].lower()

        try:
            if cmd == "ls":
                items = manager.vl.ls()
                print("Contents:", ", ".join(items) if items else "(empty)")

            elif cmd == "cd":
                if len(parts) != 2:
                    print("Usage: cd <directory>")
                    continue
                manager.vl.cd(parts[1])

            elif cmd == "pwd":
                print(manager.vl.pwd())

            elif cmd == "tree":
                manager.vl.tree()
                print('')

            elif cmd == "add":
                if len(parts) != 3:
                    print("Usage: add <name> <real_path>")
                    continue

                real_path = Path(parts[2])
                if parts[2] == "gui":
                    root = tk.Tk()
                    root.withdraw()
                    root.wm_attributes("-topmost", True)
                    real_path = filedialog.askopenfilename()
                    root.destroy()

                virtual_path = "/".join(manager.vl.path_stack + [parts[1]])
                success = manager.lm.add(virtual_path, real_path)

                if success:
                # regenerate tree
                    manager.tree = build_library_tree(manager.lm.map)
                    manager.vl.root = manager.tree
                    manager.vl.cwd = manager.vl._resolve_path(manager.vl.path_stack)
                    print(f"Added: {virtual_path} -> {real_path}")


            elif cmd == "remove":
                if len(parts) != 2:
                    print("Usage: remove <name>")
                    continue
                virtual_path = "/".join(manager.vl.path_stack + [parts[1]])
                manager.lm.remove(virtual_path)

                # Rebuild the tree after removal
                manager.tree = build_library_tree(manager.lm.map)
                manager.vl.root = manager.tree

                # Try to resolve current path stack
                try:
                    manager.vl.cwd = manager.vl._resolve_path(manager.vl.path_stack)
                except KeyError:
                    # Directory is gone, pop up one level
                    if manager.vl.path_stack:
                        manager.vl.path_stack.pop()
                        manager.vl.cwd = manager.vl._resolve_path(manager.vl.path_stack)
                    else:
                        # Already at root
                        manager.vl.cwd = manager.vl.root
                print(f"Removed: {virtual_path}")

            elif cmd == "rename":
                if len(parts) != 3:
                    print("Usage: rename <old> <new>")
                    continue
                old_path = "/".join(manager.vl.path_stack + [parts[1]])
                new_path = "/".join(manager.vl.path_stack + [parts[2]])
                manager.lm.rename(old_path, new_path)
                manager.tree = build_library_tree(manager.lm.map)
                manager.vl.root = manager.tree
                manager.vl.cwd = manager.vl._resolve_path(manager.vl.path_stack)
                print(f"Renamed: {old_path} -> {new_path}")

            elif cmd == "save":
                manager.lm.save()
                print(f"Map saved to {manager.lm.path}")

            elif cmd == "exit":
                print("Exiting map manager.")
                return

            else:
                print("Unknown command.")

        except Exception as e:
            print("Error:", e)
