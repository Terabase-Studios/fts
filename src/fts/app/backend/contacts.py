import asyncio
import ipaddress
import json
import os
import socket
import sys
import threading
import time
from typing import Any
from typing import Union, List

import psutil

from fts.app.config import CONTACTS_FILE, SEEN_IPS_FILE, DISCOVERY_PORT

# Known “fake” subnets used by hypervisors
VIRTUAL_IP_RANGES  = [
    ipaddress.ip_network("192.168.56.0/24"),  # VirtualBox Host-only
    ipaddress.ip_network("192.168.99.0/24"),  # Docker default (old)
    ipaddress.ip_network("10.0.2.0/24"),      # VirtualBox NAT
    ipaddress.ip_network("172.22.128.0/24"),
    ipaddress.ip_network("10.0.3.0/24"),
]

DISCOVERY_MESSAGE = b"FTSCHECK123"
DISCOVERY_RESPOND = b"FTSRECIEVE456"
WHO_IS_MESSAGE = b"FTSWHOIS123"
WHO_IS_RESPOND = b"FTSTHISISE456"

class OnlineUsers:
    def __init__(self):
        self.lock = threading.Lock()
        self.online: list[str] = []

    def set_online(self, users: list[str]):
        with self.lock:
            self.online = users.copy()

    def get_online(self) -> list[str]:
        with self.lock:
            return self.online.copy()

# Global instance
ONLINE_USERS = OnlineUsers()

def get_contacts():
    try:
        json_str: str = open(CONTACTS_FILE).read()
        contacts: list = json.loads(json_str).values()
        return contacts
    except:
        return []

def add_contact(name: str, value: str):
    try:
        json_str: str = open(CONTACTS_FILE).read()
        contacts: dict = json.loads(json_str)
    except:
        contacts = {}

    contacts[value] = name.strip().replace(" ", "_")

    with open(CONTACTS_FILE, "w") as f:
        json.dump(contacts, f)


def remove_contact(name: str):
    try:
        json_str: str = open(CONTACTS_FILE).read()
        contacts: dict = json.loads(json_str)
    except:
        contacts = {}

    del contacts[list(contacts.keys())[list(contacts.values()).index(name)]]

    with open(CONTACTS_FILE, "w") as f:
        json.dump(contacts, f)

def get_seen_users():
    if os.path.exists(SEEN_IPS_FILE):
        try:
            with open(SEEN_IPS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    return []

def get_users():
    global ONLINE_USERS
    # Discover current online users
    online_users: list = discover()

    # Load previously seen users from SEEN_IPS_FILE
    seen_users = get_seen_users()

    # Merge old and new users, avoiding duplicates
    all_seen_users = list(dict.fromkeys(seen_users + online_users))  # preserves order, removes duplicates

    # Save updated list
    with open(SEEN_IPS_FILE, "w") as f:
        json.dump(all_seen_users, f)

    # Prepare online/offline lists
    raw_online_users = online_users
    raw_offline_users = [x for x in seen_users if x not in online_users]

    # Load contacts
    try:
        with open(CONTACTS_FILE, "r") as f:
            contacts: dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        contacts = {}

    # Replace users with contact names, putting mapped users first
    def map_users(users):
        mapped = [contacts[u] for u in users if u in contacts]
        unmapped = [u for u in users if u not in contacts]
        return mapped + unmapped

    online_users_final = map_users(raw_online_users)
    offline_users_final = map_users(raw_offline_users)

    _contact_map = contacts
    # Update the global variable safely
    ONLINE_USERS.set_online(online_users_final)

    return {'online': online_users_final, 'offline': offline_users_final}


def get_user_list():
    users = get_users()
    users_list = users['online'] + users['offline']
    return users_list


def load_contacts() -> dict[str, str]:
    """Load contacts dictionary from file safely."""
    try:
        with open(CONTACTS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def replace_with_contact(to_replace: Union[str, List[str]]) -> Union[str, List[str]]:
    """Replace IP(s) with contact name(s)."""
    contacts = load_contacts()
    if isinstance(to_replace, list):
        return [contacts.get(item, item) for item in to_replace]
    try:
        return contacts.get(str(to_replace), to_replace)
    except Exception:
        return to_replace


def replace_with_ip(to_replace: Union[str, List[str]]) -> Union[str, List[str]]:
    """Replace contact name(s) with IP(s)."""
    contacts = load_contacts()
    # invert the dictionary: contact name -> IP
    inverted = {v: k for k, v in contacts.items()}

    if isinstance(to_replace, list):
        return [inverted.get(item, item) for item in to_replace]
    try:
        return inverted.get(str(to_replace), to_replace)
    except Exception:
        return to_replace


def is_phantom(iface_name: str) -> bool:
    """
    Returns True if the interface is likely a virtual/phantom adapter (VirtualBox, Docker, etc.)
    """
    addrs = psutil.net_if_addrs().get(iface_name, [])
    stats = psutil.net_if_stats().get(iface_name)

    # Missing stats or down interface = phantom
    if not stats or not stats.isup:
        return True

    # Zero speed = likely phantom
    if stats.speed == 0:
        return True

    for addr in addrs:
        try:
            ip = ipaddress.IPv4Address(addr.address)
            # Ignore loopback and link-local
            if ip.is_loopback or ip.is_link_local:
                continue

            # Check if the IP is in a known virtual subnet
            for vnet in VIRTUAL_IP_RANGES:
                if ip in vnet:
                    return True  # IP in virtual range → phantom

            # Otherwise, private IP not in virtual range → likely real LAN
            if ip.is_private:
                return False
        except ValueError:
            continue

    # No usable IP found → phantom
    return True


def get_broadcast_addresses():
    """
    Returns broadcast addresses for all private IPv4 interfaces, filtered for usable LAN only.
    """
    broadcasts = set()

    for iface, addrs in psutil.net_if_addrs().items():
        if is_phantom(iface):
            continue
        for addr in addrs:
            if addr.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.IPv4Address(addr.address)
                if not ip.is_private:
                    continue  # skip public IPs

                netmask = ipaddress.IPv4Address(addr.netmask if addr.netmask else "255.255.255.0")
                broadcast_int = int(ip) | (~int(netmask) & 0xFFFFFFFF)
                broadcast_addr = str(ipaddress.IPv4Address(broadcast_int))

                # Filter out link-local (169.254.x.x) and loopback (127.x.x.x) broadcasts
                if ip.is_loopback or ip.is_link_local:
                    continue

                broadcasts.add(broadcast_addr)
            except ValueError:
                continue

    return list(broadcasts)


def has_public_broadcast(broadcast_list):
    """
    Returns True if any broadcast address in the list is public.
    """
    for b in broadcast_list:
        try:
            ip = ipaddress.IPv4Address(b)
            if not ip.is_private:
                return True
        except ValueError:
            continue  # skip invalid IPs
    return False


class DiscoveryCollector(asyncio.DatagramProtocol):
    def __init__(self):
        self.responses = []

    def datagram_received(self, data, addr):
        if data == DISCOVERY_RESPOND:
            self.responses.append(addr[0])


def discover(timeout=0.1) -> list[Any] | None:
    class DiscoveryCollector:
        def __init__(self):
            self.responses = []

    collector = DiscoveryCollector()

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", 0))  # OS assigns a free port
    sock.settimeout(timeout)

    broadcasts: list[str] = get_broadcast_addresses()

    try:
        for baddr in broadcasts:
            if has_public_broadcast(baddr):
                return []
            sock.sendto(DISCOVERY_MESSAGE, (baddr, DISCOVERY_PORT))

        # Collect responses for the timeout period
        start = time.time()
        while True:
            remaining = timeout - (time.time() - start)
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                data, addr = sock.recvfrom(1024)
                if data == DISCOVERY_RESPOND:
                    collector.responses.append(addr[0])
            except socket.timeout:
                break

    finally:
        sock.close()

    return list(set(collector.responses))


class DiscoveryResponder(asyncio.DatagramProtocol):
    """Responds to discovery broadcasts from other devices."""

    def datagram_received(self, data, addr):
        if data == DISCOVERY_MESSAGE:
            self.transport.sendto(DISCOVERY_RESPOND, addr)
        elif data.startswith(WHO_IS_MESSAGE):
            pass

    def connection_made(self, transport):
        self.transport = transport


def start_discovery_responder():
    """Run the discovery responder in its own asyncio event loop on a separate thread."""

    async def _run_responder():
        loop = asyncio.get_event_loop()
        success = False
        while not success:
            try:
                transport, protocol = await loop.create_datagram_endpoint(
                    lambda: DiscoveryResponder(),
                    local_addr=("0.0.0.0", DISCOVERY_PORT),
                    allow_broadcast=True,
                )
            except:
                success = False
                time.sleep(1)
            else:
                success = True
        try:
            await asyncio.Future()  # Run forever
        finally:
            transport.close()

    def _thread_target():
        asyncio.run(_run_responder())

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    return thread