import os
import sys
import time
import socket
import subprocess

import fts.app.backend.chat as fts_chat
from fts.app.config import PLUGIN_DIR, CHAT_FILE
from textual.app import App

from fts.app.backend.contacts import replace_with_ip
from fts.app.config import CHAT_PORT
from fts.app.backend.chat import MUTED_USERS

import psutil
import json

BOOT_PRIORITY = 3

VERSION = "1.1"
OFFLINE_CONFIG = os.path.expanduser("~/.fts/app/plugins/offline_config.json")
PID_PATH = os.path.join(PLUGIN_DIR, "offline_listener.pid")
LOCK_FILE = os.path.join(PLUGIN_DIR, "offline_listener.lock")

OFFLINE_CHAT_FILE = os.path.join(PLUGIN_DIR, "offline_chat.json")

LISTENER_PATH = os.path.join(PLUGIN_DIR, "offline_chat_bg_no_include.py")
LISTENER_SCRIPT = """
import time
from fts.app.backend.contacts import replace_with_ip, replace_with_contact
from fts.app.backend.chat import MUTED_USERS, CHAT_KEY

import socket
import threading
import json
import random
import colorsys
import os
import time

OFFLINE_CONFIG = os.path.expanduser("~/.fts/app/plugins/offline_config.json")

cfg = json.load(open(OFFLINE_CONFIG))
CHAT_PORT = cfg["port"]
CHAT_FILE = cfg["chat_file"]


def color_for_sender(sender: str) -> str:
    # Create a stable RNG seeded by the sender string
    seed = hash(sender) & 0xFFFFFFFF  # ensure it's positive and fits 32 bits
    rng = random.Random(seed)

    # Choose hue deterministically; fix saturation and brightness for readability
    hue = rng.random()
    sat = 0.75
    val = 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

def on_udp_message(data: bytes, addr):
    if not data.startswith(CHAT_KEY):
        return  # ignore non-chat packets

    try:
        with open(CHAT_FILE, "r") as f:
            lines = json.load(f)
    except Exception:
        lines = []

    message = data[len(CHAT_KEY):].decode("utf-8", errors="ignore")
    sender = replace_with_contact(addr[0])

    color = color_for_sender(sender)
    line = f"[bold {color}]{sender}:[/bold {color}] {message}"
    lines.append(line)

    with open(CHAT_FILE, "w") as f:
        json.dump(lines, f)


def start_chat_listener(port=CHAT_PORT):
    from fts.app.config import logger as app_logger
    # Remove handlers to clean up resources
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)
        handler.close()
    del app_logger
    time.sleep(3)

    def listen():
        sock = None
        while sock is None:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind(("", port))
            except OSError as e:
                print(f"Socket bind failed ({e}), retrying in 1 second...")
                time.sleep(1)
                sock = None

        print(f"Chat listener bound to port {port}")

        while True:
            try:
                data, addr = sock.recvfrom(4096)
                if addr[0] not in replace_with_ip(MUTED_USERS.get_muted()):
                    on_udp_message(data, addr)
            except Exception as e:
                print("UDP listener error:", e)
                time.sleep(0.1)  # avoid tight error loop

    threading.Thread(target=listen, daemon=True).start()

    # Keep process alive
    while True:
        time.sleep(1)


if __name__ == "__main__":
    start_chat_listener()
"""

def kill_old_listener():
    if not os.path.exists(PID_PATH):
        return

    try:
        with open(PID_PATH, "r") as f:
            pid = int(f.read().strip())
    except:
        return

    try:
        p = psutil.Process(pid)
        p.terminate()
    except psutil.NoSuchProcess:
        pass
    except:
        pass

    try:
        os.remove(PID_PATH)
    except:
        pass


def start_detached_listener():

    try:
        try:
            os.remove(LISTENER_PATH)
        except:
            pass
        with open(LISTENER_PATH, "w") as f:
            f.write(LISTENER_SCRIPT)
    except Exception as e:
        print(f"[OfflineChat] failed to create {LISTENER_PATH}: {e}")
        return

    try:
        # DETACHED PROCESS (Windows)
        DETACHED = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            [sys.executable, LISTENER_PATH],
            creationflags=DETACHED,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True
        )

        with open(PID_PATH, "w") as f:
            f.write(str(proc.pid))

    except Exception as e:
        raise e


def make_config():
    try:
        cfg = json.load(open(OFFLINE_CONFIG))
        version = cfg["version"]
    except:
        version = 0

    if version != VERSION:
        try:
            os.remove(OFFLINE_CONFIG)
            print("[OfflineChat] config version mismatch\nResetting config")
        except Exception:
            pass

    listener_config = {
        "port": CHAT_PORT,
        "chat_file": str(OFFLINE_CHAT_FILE),
        "lock_file": LOCK_FILE,
        "version": str(VERSION)

    }
    with open(OFFLINE_CONFIG, "w") as f:
        json.dump(listener_config, f)


def add_offline_messages():
    try:
        with open(CHAT_FILE, "r") as f:
            lines = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        lines = []

    try:
        with open(OFFLINE_CHAT_FILE, "r") as f:
            offline_lines = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        offline_lines = []

    if not offline_lines:
        return

    lines.append(f"{"-" * 40}[OfflineChat]{"-" * 40}")
    for offline_line in offline_lines:
        lines.append(offline_line)
    lines.append(f"{"-" * 93}")

    with open(CHAT_FILE, "w") as f:
        json.dump(lines, f)

    os.remove(OFFLINE_CHAT_FILE)


def chat_listener(app: App, port: int, callback):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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


def setup_plugin():
    fts_chat.chat_listener = chat_listener
    kill_old_listener()
    make_config()
    add_offline_messages()
    start_detached_listener()