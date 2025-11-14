import os
import sys
import subprocess
from fts.app.config import PLUGIN_DIR



LISTENER_PATH = os.path.join(PLUGIN_DIR, "offline_chat_bg_no_include.py")
LISTENER_SCRIPT = """
import time
from fts.app.backend.contacts import replace_with_ip, replace_with_contact
from fts.app.backend.chat import MUTED_USERS, CHAT_KEY
from fts.app.config import CHAT_PORT, CHAT_FILE

import socket
import threading
import json
import random
import colorsys

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
    except json.JSONDecodeError:
        return
    except FileNotFoundError:
        lines = []

    message = data[len(CHAT_KEY):].decode("utf-8", errors="ignore")
    sender = replace_with_contact(addr[0])

    color = color_for_sender(sender)
    line = f"[bold {color}]{sender}:[/bold {color}] {message}"
    lines.append(line)

    with open(CHAT_FILE, "w") as f:
        json.dump(lines, f)

def start_chat_listener(port=CHAT_PORT):
    def listen():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", port))

        while True:
            try:
                data, addr = sock.recvfrom(4096)
                if addr[0] not in replace_with_ip(MUTED_USERS.get_muted()):
                    on_udp_message(data, addr)
            except:
                pass

    #t = threading.Thread(target=listen, daemon=True)
    #t.start()
    listen()

    # Keep process alive
    while True:
        time.sleep(1)

if __name__ == "__main__":
    start_chat_listener()
"""

def start_detached_listener():

    try:
        try:
            os.remove(LISTENER_PATH)
        except:
            pass
        with open(LISTENER_PATH, "w") as f:
            f.write(LISTENER_SCRIPT)
        print(f"[OfflineChat] created {LISTENER_PATH}")
    except Exception as e:
        print(f"[OfflineChat] failed to create {LISTENER_PATH}: {e}")
        return

    try:
        # DETACHED PROCESS (Windows)
        DETACHED = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(
            [sys.executable, LISTENER_PATH],
            creationflags=DETACHED,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True
        )
        print(f"[OfflineChat] started listener")
    except Exception as e:
        print(f"[OfflineChat] failed to start listener: {e}")


def setup_plugin():
    start_detached_listener()

#TODO: Print start of offline
#TODO: kill old process and create new one if exists

