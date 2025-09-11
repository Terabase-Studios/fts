import json
from pathlib import Path

class LibraryMap:
    """
    Represents a library map: virtual library path -> real system path.
    Acts as the 'private key' for the secure library tree.
    """
    def __init__(self, path=None):
        self.map = {}  # library_path -> real_path
        self.path = Path(path) if path else None
        if self.path and self.path.exists():
            self.load(self.path)

    def load(self, path: Path):
        """Load map from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            self.map = json.load(f)

    def save(self, path: Path = None):
        """Save map to JSON file."""
        path = path or self.path
        if not path:
            raise ValueError("No path specified to save the map")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.map, f, indent=4)

    def add(self, lib_path: str, real_path: str):
        """Add a new mapping with validation."""
        lib_path = lib_path.strip("/")

        # Validate virtual path
        if ".." in lib_path or lib_path.startswith("/"):
            raise ValueError("Invalid virtual path")

        # Validate real path
        warn = False
        if real_path:
            path_obj = Path(real_path).expanduser().resolve()
            if not path_obj.exists():
                print(f"Warning: real path does not exist -> {real_path}")
                warn = True
            elif path_obj.is_file():
                pass  # valid file
            elif path_obj.is_dir():
                print(f"Warning: the real path is a dir not a file -> {real_path}")
                warn = True
            real_path = str(path_obj)  # normalize path

        # Ask for confirmation
        try:
            if warn:
                response = input(f"Add anyway? [y/N]: ")
                if response.lower() != "y":
                    print("Mapping not added.")
                    return False
        except KeyboardInterrupt:
            return False

        # Save mapping
        self.map[lib_path] = real_path
        return True

    def remove(self, lib_path: str):
        """Remove a mapping by library path."""
        lib_path = lib_path.strip("/")
        if lib_path in self.map:
            del self.map[lib_path]
        else:
            raise ValueError("Invalid virtual path")

    def rename(self, old_lib_path: str, new_lib_path: str):
        """Rename a virtual path in the map."""
        old_lib_path = old_lib_path.strip("/")
        new_lib_path = new_lib_path.strip("/")
        if old_lib_path not in self.map:
            raise KeyError(f"{old_lib_path} not found in map")
        self.map[new_lib_path] = self.map.pop(old_lib_path)

    def get_real_path(self, lib_path: str) -> str:
        """Get the real system path for a given virtual path."""
        lib_path = lib_path.strip("/")
        return self.map.get(lib_path)

    def list_all(self):
        """Return all library paths in sorted order."""
        return sorted(self.map.keys())