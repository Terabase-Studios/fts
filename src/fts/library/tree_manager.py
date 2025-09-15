import shlex

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion

from fts.library.tree import VirtualLibrary


class LibraryCompleter(Completer):
    # noinspection GrazieInspection
    """
        Shell-like completer for VirtualLibrary:
        - cd: completes directories, supports nested paths, adds '/' after directories, suggests '..'
        - select: completes files, supports nested paths
        - other commands: fixed completions
        """
    def __init__(self, vl):
        self.vl = vl
        self.commands = ["ls", "cd", "pwd", "tree", "select", "exit"]

    def get_completions(self, document, complete_event):
        try:
            text = document.text_before_cursor.lstrip()
            parts = shlex.split(text)

            if not parts:
                for cmd in self.commands:
                    yield Completion(cmd, start_position=0)
                return

            cmd = parts[0].lower()

            # Completing command itself
            if len(parts) == 1 and not text.endswith(" "):
                for c in self.commands:
                    if c.startswith(cmd):
                        yield Completion(c, start_position=-len(cmd))
                return

            # Everything after command
            arg = text[len(parts[0]):].lstrip()

            # Helper: traverse a dictionary node based on a path string
            def resolve_path(path, start_node):
                node = start_node
                components = path.split("/")
                for comp in components[:-1]:
                    if comp == "..":
                        node = self.vl.get_parent(node)
                    elif comp in node and node[comp]:
                        node = node[comp]
                    else:
                        return None, components[-1]
                last = components[-1] if components else ""
                return node, last

            # noinspection GrazieInspection
            if cmd == "cd":
                base_node, last = resolve_path(arg, self.vl.cwd)
                if base_node is None:
                    return

                for name, value in base_node.items():
                    if value and name.startswith(last):
                        completion_text = "/".join(arg.split("/")[:-1] + [name])
                        yield Completion(completion_text, start_position=-len(arg))

                # Suggest '..' if not at root
                if self.vl.cwd != self.vl.root:
                    yield Completion("..", start_position=-len(last))

            elif cmd == "select":
                base_node, last = resolve_path(arg, self.vl.cwd)
                if base_node is None:
                    return

                # Recursive helper to collect all files under a node with their relative paths
                def collect_files(node, prefix=""):
                    results = []
                    for name, value in node.items():
                        path = f"{prefix}/{name}" if prefix else name
                        if value: # Directory
                            results.extend(collect_files(value, path))
                        else:     # File
                            results.append(path)
                    return results

                files = collect_files(base_node)
                # Filter by what the user has typed and sort by depth
                for f in sorted(files, key=lambda x: x.count("/")):
                    if f.startswith(last):
                        # Prepend any path components before last in arg
                        completion_text = "/".join(arg.split("/")[:-1] + [f])
                        yield Completion(completion_text, start_position=-len(arg))
        except:
            return



def browse_library(library_tree: dict) -> str:
    """
    Interactive library browser using Prompt Toolkit.
    Provides command-line style navigation and file selection.

    Returns:
        str: The selected file's library path.
    """
    vl = VirtualLibrary(library_tree)
    session = PromptSession()
    completer = LibraryCompleter(vl)

    print("Welcome to the Virtual Library!")
    print("Commands: ls, cd <dir>, cd .., pwd, tree, select <file>, exit")
    print("Library structure:")
    vl.tree()
    print('')

    while True:
        try:
            command = session.prompt(f"[{vl.pwd()}] > ", completer=completer, complete_while_typing=True).strip()
        except KeyboardInterrupt:
            return ""
        except EOFError:
            print("\nExiting library browser...")
            return ""

        if not command:
            continue

        parts = shlex.split(command)
        cmd = parts[0].lower()

        try:
            if cmd == "ls":
                items = vl.ls()
                print("Contents:", ", ".join(items) if items else "(empty)")

            elif cmd == "cd":
                if len(parts) != 2:
                    print("Usage: cd <directory>")
                    continue
                vl.cd(parts[1])

            elif cmd == "pwd":
                print(vl.pwd())

            elif cmd == "tree":
                vl.tree()
                print('')

            elif cmd == "select":
                if len(parts) != 2:
                    print("Usage: select <file>")
                    continue
                lib_path = vl.get_file_path(parts[1])
                print(f"Selected file: {lib_path}")
                return lib_path

            elif cmd == "exit":
                print("Exiting library browser.")
                return ""

            else:
                print("Unknown command. Use: ls, cd <dir>, pwd, tree, select <file>, exit")

        except (FileNotFoundError, NotADirectoryError) as e:
            print("Error:", e)

    return ''