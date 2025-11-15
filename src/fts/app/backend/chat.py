import json
import time
import socket
import threading

from textual.app import App

from fts.app.backend.contacts import get_broadcast_addresses, has_public_broadcast, replace_with_ip
from fts.app.config import CHAT_PORT, MUTED_FILE

CHAT_KEY: bytes = b"FTSCHATMSG"

class MutedUsers:
    def __init__(self, file_path: str):
        self.lock = threading.Lock()
        self.file_path = file_path

        try:
            with open(file_path, "r") as f:
                self.muted: list[str] = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.muted: list[str] = []

    def set_muted(self, users: list[str]):
        with self.lock:
            self.muted = users.copy()
            with open(self.file_path, "w") as f:
                json.dump(self.muted, f)

    def get_muted(self) -> list[str]:
        with self.lock:
            return self.muted.copy()

# Global instance
MUTED_USERS = MutedUsers(MUTED_FILE)

def send(msg, timeout=0.5) -> str:
    try:
        msg = CHAT_KEY + bytes(str(msg), "utf-8")
    except:
        return "failed to convert message to utf-16"

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", 0))  # OS assigns a free port
    sock.settimeout(timeout)

    broadcasts = get_broadcast_addresses()
    try:
        for baddr in broadcasts:
            if has_public_broadcast(baddr):
                return "no public broadcast allowed"
            sock.sendto(msg, (baddr, CHAT_PORT))
    except Exception as e:
        sock.close()
        return e

    sock.close()
    return ""


def chat_listener(app: App, port: int, callback):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", port))
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            if addr[0].strip() not in replace_with_ip(MUTED_USERS.get_muted()):
                app.call_from_thread(callback, data, addr)
        except Exception as e:
            print("UDP listener error:", e)
            time.sleep(0.1)
            continue

def start_chat_listener(app: App, port: int, callback):
    """
    Start a background thread that listens for UDP broadcast packets.
    Calls `callback(data, addr)` on the main thread.
    """
    thread = threading.Thread(target=chat_listener, daemon=True, args=(app, port, callback))
    thread.start()
    return thread


