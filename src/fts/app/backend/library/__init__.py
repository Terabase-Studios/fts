import os
import json
import hashlib
import sys
from typing import Dict, Any

from fts.app.backend.library.config import LIBRARY_PATH, LIBRARY_CACHE_FILE, IGNORE_HIDDEN_FOLDERS


class FTSLibrary:
    def __init__(self, library_root: str = LIBRARY_PATH, cache_file: str = LIBRARY_CACHE_FILE):
        self.library_root = os.path.abspath(library_root)
        self.cache_file = cache_file
        self.id_index: Dict[str, Dict[str, Any]] = {}  # id -> file info
        self.path_index: Dict[str, str] = {}          # path -> id
        self.tree: Dict[str, Any] = {}               # nested folder tree

        # Load cache if exists, else full build
        if os.path.exists(self.cache_file):
            self._load_cache()
            self.update()
        else:
            self.build_index()
            self._save_cache()

    def build_index(self):
        """Full rebuild of the library."""
        self.id_index.clear()
        self.path_index.clear()
        self.tree.clear()

        for root, dirs, files in os.walk(self.library_root):
            if IGNORE_HIDDEN_FOLDERS:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]

            rel_path = os.path.relpath(root, self.library_root)
            node = self._get_tree_node(rel_path)

            for fname in files:
                fpath = os.path.join(root, fname)
                self._add_file(node, fpath, rel_path)

    def _add_file(self, node: Dict[str, Any], fpath: str, rel_path: str):
        """Add a single file to the tree and indexes."""
        fsize = os.path.getsize(fpath)
        fid = self._generate_id(fpath)
        file_info = {
            "name": os.path.basename(fpath),
            "size": fsize,
            "id": fid,
            "path": os.path.join(rel_path, os.path.basename(fpath))
        }
        node.setdefault("files", []).append(file_info)
        self.id_index[fid] = file_info
        self.path_index[fpath] = fid

    def _get_tree_node(self, rel_path: str) -> Dict[str, Any]:
        node = self.tree
        if rel_path != ".":
            for part in rel_path.split(os.sep):
                node = node.setdefault(part, {})
        return node

    def _generate_id(self, fpath: str) -> str:
        h = hashlib.sha256()
        h.update(fpath.encode("utf-8"))
        h.update(str(os.path.getsize(fpath)).encode("utf-8"))
        return h.hexdigest()[:16]

    def refresh(self):
        """Full rebuild."""
        self.build_index()
        self._save_cache()

    def update(self):
        """Incrementally update the library and cache."""
        current_files = {}
        for root, dirs, files in os.walk(self.library_root):
            if IGNORE_HIDDEN_FOLDERS:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]
            for fname in files:
                fpath = os.path.join(root, fname)
                current_files[fpath] = os.path.getsize(fpath)

        # Detect deleted files
        for fpath in list(self.path_index.keys()):
            if fpath not in current_files:
                fid = self.path_index.pop(fpath)
                self.id_index.pop(fid, None)
                self._remove_from_tree(fpath)

        # Detect new or modified files
        for fpath, fsize in current_files.items():
            fid_old = self.path_index.get(fpath)
            if fid_old is None:
                rel_path = os.path.relpath(os.path.dirname(fpath), self.library_root)
                node = self._get_tree_node(rel_path)
                self._add_file(node, fpath, rel_path)
            else:
                if self.id_index[fid_old]["size"] != fsize:
                    self.id_index[fid_old]["size"] = fsize

        self._save_cache()

    def _remove_from_tree(self, fpath: str):
        rel_path = os.path.relpath(fpath, self.library_root)
        parts = rel_path.split(os.sep)
        *folders, fname = parts

        # Traverse and keep references for pruning
        node = self.tree
        parents = []
        for part in folders:
            parents.append((node, part))
            node = node.get(part, {})
            if not node:
                return  # folder already gone

        # Remove the file
        if "files" in node:
            node["files"] = [f for f in node["files"] if f["name"] != fname]
            if not node["files"]:
                node.pop("files", None)

        # Prune empty folders from bottom to top
        for parent_node, folder_name in reversed(parents):
            child = parent_node.get(folder_name, {})
            if not child or (len(child) == 0):
                parent_node.pop(folder_name, None)

    def to_json_tree(self) -> str:
        return json.dumps(self.tree, indent=2)

    def search(self, phrase: str) -> Dict[str, Dict[str, Any]]:
        phrase_lower = phrase.lower()
        return {
            fid: {"name": info["name"], "size": info["size"], "id": fid}
            for fid, info in self.id_index.items()
            if phrase_lower in info["name"].lower()
        }

    def get_by_id(self, fid: str) -> Dict[str, Any] | None:
        return self.id_index.get(fid)

    def _save_cache(self):
        """Save tree and ID index to disk."""
        cache_data = {
            "path": self.library_root,
            "tree": self.tree,
            "id_index": self.id_index,
            "path_index": self.path_index
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)

    def _load_cache(self):
        """Load tree and indexes from disk."""
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
        except:
            cache_data = {}
        cached_root = cache_data["path"]
        if self.library_root != cached_root:
            self.refresh()
            return
        self.tree = cache_data.get("tree", {})
        self.id_index = cache_data.get("id_index", {})
        self.path_index = cache_data.get("path_index", {})

    def id_to_filepath(self, id: str) -> str:
        rel_path = self.get_by_id(id).get("path", None)
        if not rel_path:
            return None

        abs_path = os.path.join(str(self.library_root), str(rel_path)).replace("\\.\\", "\\")
        return abs_path