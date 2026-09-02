import asyncio
import ipaddress
import json
import os
import socket
import threading
import time
from typing import Union, List

import psutil

from fts.app.cache import CONTACTS_FILE, MUTED_FILE, SEEN_IPS_FILE, PLUGIN_DIR, MAC_FILE
from fts.app.config import DISCOVERY_PORT, logger, IP_REMAPPING_WITH_MAC
from fts.core.secure import get_ip_to_mac
from fts.core.utilities import run_async

FILES_TO_UPDATE_IP = [CONTACTS_FILE, MUTED_FILE, SEEN_IPS_FILE, os.path.join(PLUGIN_DIR, "ip_blacklist.txt")]
DISCOVERY_TIMEOUT = 3.0  # seconds

VIRTUAL_IP_RANGES = [
    ipaddress.ip_network("192.168.56.0/24"),
    ipaddress.ip_network("192.168.99.0/24"),
    ipaddress.ip_network("10.0.2.0/24"),
    ipaddress.ip_network("172.22.128.0/24"),
    ipaddress.ip_network("10.0.3.0/24"),
]

DISCOVERY_MESSAGE = b"FTSCHECK123"
DISCOVERY_RESPOND = b"FTSRECIEVE456"
WHO_IS_MESSAGE = b"FTSWHOIS123"
WHO_IS_RESPOND = b"FTSTHISIS456"


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
    return False


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
        if data.startswith(DISCOVERY_RESPOND):
            self.responses.append(addr[0])


def discover(timeout=DISCOVERY_TIMEOUT, get_macs=True):
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
                if data.startswith(DISCOVERY_RESPOND):
                    ip = addr[0]
                    if get_macs:
                        mac_data = data.removeprefix(DISCOVERY_RESPOND)
                        if mac_data:
                            potential_macs = json.loads(mac_data)
                            mac = potential_macs.get(ip, None)
                            macs = {}
                            try:
                                with open(MAC_FILE, "r") as f:
                                    macs = json.load(f)
                            except:
                                macs = {}
                            if IP_REMAPPING_WITH_MAC:
                                if mac in macs and macs[mac] != ip:
                                    logger.info(f"[Discoverer][Mac] Ip update: {macs[mac]} -> {ip}")
                                    update_ip(macs[mac], ip)
                                macs[mac] = ip
                            elif not mac in macs:
                                macs[mac] = ip
                            with open(MAC_FILE, "w") as f:
                                json.dump(macs, f)
                    collector.responses.append(ip)
            except socket.timeout:
                break

    finally:
        sock.close()

    return list(set(collector.responses))


def update_ip(old_ip: str, new_ip: str):
    from pathlib import Path
    for file_path in FILES_TO_UPDATE_IP:
        path = Path(file_path)
        if not path.is_file():
            print(f"Skipping {file_path}, not a file.")
            continue

        # Read the file
        text = path.read_text(encoding="utf-8")

        # Replace all occurrences
        text = text.replace(old_ip, new_ip)

        # Write back
        path.write_text(text, encoding="utf-8")


class DiscoveryResponder(asyncio.DatagramProtocol):
    """Responds to discovery broadcasts from other devices."""

    def datagram_received(self, data, addr):
        if data == DISCOVERY_MESSAGE:
            self.transport.sendto(DISCOVERY_RESPOND + bytes(json.dumps(get_ip_to_mac()), 'utf-8'), addr)
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
        run_async(_run_responder())

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    return thread
