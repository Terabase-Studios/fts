import asyncio
import random
import psutil
import socket
import threading
import time

from fts.app.backend.contacts import start_discovery_responder, ONLINE_USERS, get_users, replace_with_ip, get_user_list
from fts.app.config import logger

def get_all_ip_addresses():
    """
    Retrieves all IPv4 and IPv6 addresses associated with the system's network interfaces.
    """
    ip_addresses = {}
    for interface, snics in psutil.net_if_addrs().items():
        ipv4_addresses = []
        ipv6_addresses = []
        for snic in snics:
            if snic.family == socket.AF_INET:  # IPv4
                ipv4_addresses.append(snic.address)
            elif snic.family == socket.AF_INET6:  # IPv6
                ipv6_addresses.append(snic.address)
        if ipv4_addresses:
            ip_addresses[interface] = {'ipv4': ipv4_addresses, 'ipv6': ipv6_addresses}
        elif ipv6_addresses:
            ip_addresses[interface] = {'ipv6': ipv6_addresses}
    return ip_addresses

def get_ip():
    all_ips = get_all_ip_addresses()
    for interface, addresses in all_ips.items():
        if not 'ipv4' in addresses:
            return

        for addr in addresses['ipv4']:
            if addr in replace_with_ip(ONLINE_USERS.get_online()):
                return addr

    return None


class HostManager:
    def __init__(self, ip=get_ip(), online_getter=ONLINE_USERS.get_online):
        self.ip = ip
        self.get_online = online_getter  # returns current online IPs

        self._lock = threading.Lock()
        self._host_ip = None
        self.is_host = False

        self.host_changed_funcs = []
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._running = False

    # Public thread-safe getter
    def get_host_ip(self):
        with self._lock:
            return self._host_ip

    def _safe_get_online_ips(self):
        try:
            online = self.get_online()
            if not online:
                return []
            return replace_with_ip(online) or []
        except Exception as e:
            logger.error(f"[HostManager][{self.ip}] get_online() error: {e}")
            return []

    def _run(self):
        logger.debug(f"[HostManager] Awaiting IP")
        while self._running and not self.ip:
            self.ip = get_ip()
            time.sleep(.1)
            continue
        logger.debug(f"[HostManager][{self.ip}] IP found")

        while self._running:
            online_ips = self._safe_get_online_ips()

            if online_ips:
                new_host = min(online_ips)

                with self._lock:
                    old_host = self._host_ip

                    if new_host != old_host:
                        logger.info(f"[HostManager][{self.ip}] Host changed: {old_host} -> {new_host}")
                        self._host_ip = new_host
                        self.is_host = (self.ip == new_host)

                        # Copy to avoid external modification during iteration
                        callbacks = list(self.host_changed_funcs)

                # Callbacks outside lock to avoid deadlocks
                if new_host != old_host and old_host:
                    for func in callbacks:
                        try:
                            func()
                        except Exception as e:
                            logger.error(f"[HostManager] callback error: {func} -> {e}")

            time.sleep(0.5)



class HostPresenceWatcher:
    def __init__(self,  online_getter=ONLINE_USERS.get_online, interval=0.5):
        """
        get_online: function returning iterable of online IPs
        interval: polling interval in seconds
        """
        self.online_getter = online_getter
        self.interval = interval
        self._known = set()
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._running = False

    def _safe_get_online(self):
        try:
            result = self.online_getter()
            if not result:
                return set()
            return set(result)
        except Exception as e:
            logger.error(f"[Watcher] Error calling online_getter(): {e}")
            return set()

    def _run(self):
        while self._running:
            with self._lock:
                current = self._safe_get_online()

                # who joined?
                joined = current - self._known

                # who left?
                left = self._known - current

                for ip in sorted(joined):
                    logger.info(f"[Watcher] User online: {ip}")

                for ip in sorted(left):
                    logger.info(f"[Watcher] User offline: {ip}")

                # update known list
                self._known = current

            time.sleep(self.interval)


host_manager = HostManager()
host_watcher = HostPresenceWatcher()