def build_library_tree(library_map: dict) -> dict:
    """
    Converts a flat library map into a nested dictionary tree.
    Leaf nodes are empty dicts; no references to actual system paths are stored.
    """
    tree = {}
    for lib_path in library_map.keys():
        parts = lib_path.strip("/").split("/")
        node = tree
        for part in parts:
            if part not in node:
                node[part] = {}
            node = node[part]  # descend into next level
    return tree


class VirtualLibrary:
    """
    Represents a virtual library based solely on the secure library tree.
    Does NOT store or expose any real paths.
    """
    def __init__(self, library_tree: dict):
        self.root = library_tree
        self.cwd = library_tree
        self.path_stack = []

    def ls(self) -> list[str]:
        """
        List the contents of the current directory.
        Directories and files are returned together, sorted alphabetically.
        """
        return sorted(self.cwd.keys())

    def cd(self, dirname: str):
        """
        Change the current working directory in the virtual library.
        Supports '..' to go up one level.
        Raises FileNotFoundError if the directory does not exist.
        """
        if dirname == "..":
            if self.path_stack:
                self.path_stack.pop()
                self.cwd = self._resolve_path(self.path_stack)
        elif dirname in self.cwd and self.cwd[dirname]:
            # Must be a directory (non-empty dict)
            self.path_stack.append(dirname)
            self.cwd = self._resolve_path(self.path_stack)
        elif dirname in self.cwd and not self.cwd[dirname]:
            # It's a file, cannot cd into a file
            raise NotADirectoryError(f"'{dirname}' is a file, not a directory")
        else:
            raise FileNotFoundError(f"No such directory: '{dirname}'")

    def pwd(self) -> str:
        """Return the current path in the virtual library."""
        return "/" + "/".join(self.path_stack)

    def get_file_path(self, path: str) -> str:
        """
        Returns the library path of a file relative to cwd.
        Supports nested paths like 'holiday/2025.png'.
        Raises FileNotFoundError if the file does not exist.
        """
        node = self.cwd
        parts = path.strip("/").split("/")
        for i, part in enumerate(parts):
            if part in node:
                node = node[part]
                if i == len(parts) - 1:  # last part
                    if node:  # directory
                        raise IsADirectoryError(f"'{path}' is a directory, not a file")
                    else:
                        return "/".join(self.path_stack + parts)
            else:
                raise FileNotFoundError(f"No such file or directory: '{path}'")
        return "/".join(self.path_stack + parts)

    def _resolve_path(self, path_list: list[str]) -> dict:
        """Internal method to descend into the library tree based on a path stack."""
        node = self.root
        for p in path_list:
            node = node[p]
        return node

    def tree(self, start_dir: str = "", max_depth: int = None):
        """
        Prints the library tree starting at 'start_dir', with optional max depth.
        """
        # Navigate to start_dir if specified
        node = self.root
        path_stack_backup = list(self.path_stack)  # Save current cwd
        if start_dir:
            parts = start_dir.strip("/").split("/")
            for part in parts:
                if part in node:
                    node = node[part]
                else:
                    print(f"Start directory '{start_dir}' not found in tree.")
                    return

        def _print_subtree(subtree, pre="", depth=0):
            if max_depth is not None and depth > max_depth:
                return
            keys = sorted(subtree.keys())
            for i, key in enumerate(keys):
                is_last = i == len(keys) - 1
                branch = "└── " if is_last else "├── "
                print(pre + branch + key)
                if subtree[key]:  # directory
                    extension = "    " if is_last else "│   "
                    _print_subtree(subtree[key], pre + extension, depth + 1)

        _print_subtree(node)

