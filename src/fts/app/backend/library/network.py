import json
import sys
import time
import asyncio
import threading
import socket
from typing import Dict, Any

from fts.app.backend.contacts import discover
import fts.app.backend.transfer as fts_transfer
from fts.app.backend.library.config import LIBRARY_PORT, LIBRARY_LOG_FILE
from fts.app.backend.library import FTSLibrary
from fts.app.config import logger
import fts.app.config as app_config

LIBRARY_DISCOVER = b"FTSLIBRARYDISCOVER"
LIBRARY_RESPONSE = b"FTSLIBRARYRESPONSE"
LIBRARY_REQUEST = b"FTSLIBRARYREQUEST"

class FTSNetLibrary:
    """
    Represents a remote FTS library received from another peer.
    """

    def __init__(self, ip: str, built_tree: dict):
        self.ip = ip
        self.tree: Dict[str, Any] = {}
        self.id_index: Dict[str, Dict[str, Any]] = {}
        self.path_index: Dict[str, str] = {}
        self.build_from_tree(built_tree)

    def build_from_tree(self, built_tree: dict):
        """
        Build the library from a received JSON-like tree.
        """
        self.tree = built_tree
        self.id_index.clear()
        self.path_index.clear()
        self._index_tree(self.tree)

    def _index_tree(self, node: dict, current_path: str = ""):
        """
        Recursively index files in the tree for fast lookup by ID and path.
        """
        for key, value in node.items():
            if key == "files":
                for f in value:
                    path = f"{current_path}/{f['name']}".lstrip("/")
                    self.id_index[f["id"]] = f
                    self.path_index[path] = f["id"]
            else:
                self._index_tree(value, f"{current_path}/{key}".lstrip("/"))

    def update(self, new_tree: dict):
        """
        Update the library if the received tree has changes.
        Returns True if changes were made.
        """
        changes_made = False

        # Compare old and new tree JSON strings for simplicity
        old_tree_json = json.dumps(self.tree, sort_keys=True)
        new_tree_json = json.dumps(new_tree, sort_keys=True)

        if old_tree_json != new_tree_json:
            self.build_from_tree(new_tree)
            changes_made = True

        return changes_made

    def to_json_tree(self) -> str:
        return json.dumps(self.tree, indent=2)

    def search(self, phrase: str) -> Dict[str, Dict[str, Any]]:
        phrase_lower = phrase.lower()
        return {
            fid: {"name": info["name"], "size": info.get("size", 0), "id": fid}
            for fid, info in self.id_index.items()
            if phrase_lower in info["name"].lower()
        }

    def get_by_id(self, fid: str) -> Dict[str, Any] | None:
        return self.id_index.get(fid)


class DiscoveryResponder:
    """TCP server that responds with library data."""

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            if not app_config.library_enabled:
                writer.close()
                await writer.wait_closed()
                return
            try:
                with open(LIBRARY_LOG_FILE, "r") as f:
                    history = json.load(f)
            except:
                history = []
            data = await reader.read(1024)  # read discovery message
            if not data:
                return
            logger.debug(f"[Library][Responder] Received {data} from {writer.get_extra_info('peername')[0]}")
            if data == LIBRARY_DISCOVER:
                library = FTSLibrary()
                response = library.to_json_tree().encode()
                # First send length, then the data
                writer.write(len(response).to_bytes(4, "big"))
                writer.write(response)
                history.append({"type": "discover", "data": data.decode(), "source": writer.get_extra_info("peername")[0]})
                with open(LIBRARY_LOG_FILE, "w") as f:
                    json.dump(history, f)
                await writer.drain()
            else:
                file_id = data[len(LIBRARY_REQUEST):].decode("utf-8").replace(" ", "")
                library = FTSLibrary()
                abs_path = library.id_to_filepath(file_id)

                ip = writer.get_extra_info('peername')[0]

                logger.info(f"[Library][Responder] Received library request from {ip}: {file_id}->{abs_path}")
                history.append({"type": "request", "data": data.decode(), "source": writer.get_extra_info("peername")[0], "id": file_id, "path": abs_path})
                with open(LIBRARY_LOG_FILE, "w") as f:
                    json.dump(history, f)

                fts_transfer.transfer_handler.send_safe(ip, abs_path, True)

        except Exception as e:
            logger.error(f"[Library][Responder] Error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def run_server(self):
        server = await asyncio.start_server(self.handle_client, "0.0.0.0", LIBRARY_PORT)
        async with server:
            await server.serve_forever()


def start_library_responder():
    """Run the TCP responder in a background thread."""
    def _thread_target():
        asyncio.run(DiscoveryResponder().run_server())

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    return thread


async def get_libraries(timeout=1):
    """Discover libraries on a list of IPs."""
    collector = []

    broadcasts = discover()
    for ip in broadcasts:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, LIBRARY_PORT), timeout)
            writer.write(LIBRARY_DISCOVER)
            await writer.drain()

            # Read length prefix
            length_bytes = await asyncio.wait_for(reader.readexactly(4), timeout)
            length = int.from_bytes(length_bytes, "big")
            data_bytes = await asyncio.wait_for(reader.readexactly(length), timeout)
            library_data = json.loads(data_bytes.decode())
            collector.append((ip, library_data))

            writer.close()
            await writer.wait_closed()
        except asyncio.TimeoutError:
            logger.debug(f"[Library][Retriever] Unreachable Host: {ip}, Error: Timeout")
            continue  # ignore unreachable hosts
        except Exception as e:
            logger.debug(f"[Library][Retriever] Unreachable Host: {ip}, Error: {e}")
            continue  # ignore unreachable hosts

    return collector

async def ask_for_file(ip, file_id, timeout=0.5):
    try:
        reader, writer = await asyncio.open_connection(ip, LIBRARY_PORT)


        writer.write(LIBRARY_REQUEST + file_id.encode("utf-8"))
        await writer.drain()

        writer.close()
        await writer.wait_closed()
        return True
    except:
        return False



