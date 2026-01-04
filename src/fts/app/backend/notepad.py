import asyncio
import threading
import socket
import json
import time
import base64
from typing import Callable
from difflib import SequenceMatcher

from pycrdt import Doc, Text

from fts.app.backend.contacts import ONLINE_USERS, replace_with_ip
from fts.app.backend.host import host_manager
from fts.app.config import logger, NOTEPAD_PORT

BUFFER_SIZE = 65536
CLIENT_TIMEOUT = 60  # seconds


def _b64encode(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64decode(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


class NotepadHost:
    """Single-host UDP distributor of pycrdt updates."""

    def __init__(self, port: int = NOTEPAD_PORT):
        self.port = port
        self.clients: dict[tuple[str, int], float] = {}  # addr -> last_seen
        self.lock = threading.Lock()
        self.running = True

        # pycrdt document
        self.doc = Doc()
        self.doc["notepad"] = Text("")  # initial empty text
        self.ytext: Text = self.doc["notepad"]

        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)  # non-blocking recv
        self.sock.bind(("", self.port))

        # asyncio loop
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        # server thread
        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()

        logger.info(f"[NotepadHost] started on UDP port {self.port}")

    def set_text(self, text):
        self.doc["notepad"] = text

    def run_server(self) -> None:
        while self.running:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"[NotepadHost] recv error: {e}")
                continue

            first_seen = False
            with self.lock:
                first_seen = addr not in self.clients
                self.clients[addr] = time.time()

            # schedule async handling
            asyncio.run_coroutine_threadsafe(
                self.handle_message(data, addr, first_seen), self.loop
            )

    async def handle_message(self, data: bytes, addr, first_seen: bool):
        if not host_manager.is_host:
            return

        try:
            payload = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return

        msg_type = payload.get("type")

        if msg_type == "crdt_update":
            update_b64 = payload.get("update")
            if not update_b64:
                return
            update_bytes = _b64decode(update_b64)

            with self.lock:
                try:
                    self.doc.apply_update(update_bytes)
                except Exception as e:
                    logger.exception(f"[NotepadHost] apply_update failed: {e}")
                    return

            await self.broadcast_update(update_bytes)

        elif msg_type == "sync_request":
            logger.debug(f"[NotepadHost] sync_request from {addr}")
            with self.lock:
                full_update = self.doc.get_update()
            msg = {"type": "crdt_update", "update": _b64encode(full_update)}
            try:
                self.sock.sendto(json.dumps(msg).encode("utf-8"), addr)
            except Exception as e:
                logger.error(f"[NotepadHost] failed to send initial state to {addr}: {e}")

    async def broadcast_update(self, update_bytes: bytes):
        if not host_manager.is_host:
            return
        now = time.time()
        dead = []

        msg = {"type": "crdt_update", "update": _b64encode(update_bytes)}
        b = json.dumps(msg).encode("utf-8")

        with self.lock:
            for client, last in list(self.clients.items()):
                try:
                    self.sock.sendto(b, client)
                except Exception as e:
                    logger.error(f"[NotepadHost] failed to send to {client}: {e}")
                if now - last > CLIENT_TIMEOUT:
                    dead.append(client)
            for d in dead:
                logger.debug(f"[NotepadHost] removing stale client {d}")
                self.clients.pop(d, None)

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except:
            pass
        self.server_thread.join(timeout=1)
        self.loop.call_soon_threadsafe(self.loop.stop)


class NotepadClient:
    def __init__(self, on_update_callback: Callable[[str], None], host_port: int = NOTEPAD_PORT):
        self.on_update_callback = on_update_callback
        self.host_port = host_port
        self.running = True
        self.suppress_send = False

        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)
        self.sock.bind(("", 0))

        # pycrdt
        self.doc = Doc()
        self.doc["notepad"] = Text("")
        self.ytext: Text = self.doc["notepad"]

        # listener thread
        self.listener_thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.listener_thread.start()

        # request full sync and apply immediately
        host_addr = (host_manager.get_host_ip(), self.host_port)
        #try:
        #    req = {"type": "sync_request"}
        #    self.sock.sendto(json.dumps(req).encode("utf-8"), host_addr)
        #except Exception as e:
        #    logger.error(f"[NotepadClient] failed to request sync: {e}")

        logger.info(f"[NotepadClient] started, host={host_addr}")


    def new_text(self, new_text: str):
        if self.suppress_send:
            return

        host_addr = (host_manager.get_host_ip(), self.host_port)

        try:
            old_text = str(self.ytext)

            matcher = SequenceMatcher(None, old_text, new_text)
            with self.doc.transaction():
                for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                    if tag in ("replace", "delete"):
                        del self.ytext[i1:i2]
                    if tag in ("replace", "insert"):
                        self.ytext.insert(i1, new_text[j1:j2])

            update_bytes = self.doc.get_update()
            msg = {"type": "crdt_update", "update": _b64encode(update_bytes)}
            self.sock.sendto(json.dumps(msg).encode("utf-8"), host_addr)

        except Exception as e:
            logger.exception(f"[NotepadClient] new_text/send failed: {e}")

    def listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"[NotepadClient] recv error: {e}")
                continue

            try:
                payload = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            if payload.get("type") != "crdt_update":
                continue

            update_b64 = payload.get("update")
            if not update_b64:
                continue
            update_bytes = _b64decode(update_b64)

            self.suppress_send = True
            try:
                self.doc.apply_update(update_bytes)
            except Exception as e:
                logger.exception(f"[NotepadClient] apply_update failed: {e}")
            finally:
                self.suppress_send = False

            # call callback with current text
            try:
                self.on_update_callback(str(self.ytext))
            except Exception as e:
                logger.exception(f"[NotepadClient] on_update_callback error: {e}")

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except:
            pass
        self.listener_thread.join(timeout=1)
