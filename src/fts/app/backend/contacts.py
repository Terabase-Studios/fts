import asyncio
import ipaddress
import json
import os
import socket
import threading
import time
from typing import Any

import psutil

from fts.app.config import CONTACTS_FILE, SEEN_IPS_FILE, DISCOVERY_PORT

DISCOVERY_MESSAGE = b"CHECK123"
DISCOVERY_RESPOND = b"RECIEVE456"

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

    contacts[value] = name

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


def get_users():
    # Discover current online users
    online_users: list = discover()

    # Load previously seen users from SEEN_IPS_FILE
    seen_users = []
    if os.path.exists(SEEN_IPS_FILE):
        try:
            with open(SEEN_IPS_FILE, "r") as f:
                seen_users = json.load(f)
        except json.JSONDecodeError:
            seen_users = []

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

    return {'online': online_users_final, 'offline': offline_users_final}


def get_user_list():
    users = get_users()
    users_list = users['online'] + users['offline']
    return users_list


def replace_with_contacts(to_replace: str | list[str]):
    # Load contacts
    try:
        with open(CONTACTS_FILE, "r") as f:
            contacts: dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        contacts = {}
    keys = list(contacts.keys())

    if to_replace is list[str]:
        new_list: list[str] = []
        for contact in to_replace:
            if contact in keys:
                new_list.append(contacts[contact])
            else:
                new_list.append(contact)

        return new_list

    try:
        to_replace = str(to_replace)
    except:
        pass

    if type(to_replace) == str:
        if to_replace in keys:
            return contacts[to_replace]
        else:
            return to_replace
    else:
        return to_replace


def get_broadcast_addresses():
    """
    Returns broadcast addresses for all private IPv4 interfaces, filtered for usable LAN only.
    """
    broadcasts = set()

    for iface, addrs in psutil.net_if_addrs().items():
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


def discover(timeout=0.5) -> list[Any] | None:
    class DiscoveryCollector:
        def __init__(self):
            self.responses = []

    collector = DiscoveryCollector()

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", 0))  # OS assigns a free port
    sock.settimeout(timeout)

    broadcasts = get_broadcast_addresses()
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

    def connection_made(self, transport):
        self.transport = transport


def start_discovery_responder():
    """Run the discovery responder in its own asyncio event loop on a separate thread."""

    async def _run_responder():
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: DiscoveryResponder(),
            local_addr=("0.0.0.0", DISCOVERY_PORT),
            allow_broadcast=True,
        )
        try:
            await asyncio.Future()  # Run forever
        finally:
            transport.close()

    def _thread_target():
        asyncio.run(_run_responder())

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    return thread