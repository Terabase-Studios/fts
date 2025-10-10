import threading
import time
from collections import deque, defaultdict
from typing import Tuple, Deque, Dict, Any

from fts.config import DOSP_ENABLED, MAX_REQS_PER_MIN, MAX_BYTES_PER_MIN, BAN_SECONDS, REQUEST_WINDOW


class _PerIPState:
    def __init__(self):
        self.req_times: Deque[float] = deque()
        self.byte_events: Deque[tuple[float,int]] = deque()  # (timestamp, bytes)
        self.banned_until = 0.0

class DDoSProtector:
    def __init__(
        self,
        max_reqs_per_min: int = MAX_REQS_PER_MIN,
        max_bytes_per_min: int = MAX_BYTES_PER_MIN,
        ban_seconds: int = BAN_SECONDS,
        window_seconds: float = REQUEST_WINDOW
    ):
        self.max_reqs = max_reqs_per_min
        self.max_bytes = max_bytes_per_min
        self.ban_seconds = ban_seconds
        self.window = window_seconds

        self._states: Dict[str, _PerIPState] = defaultdict(_PerIPState)
        self._lock = threading.Lock()

    def _cleanup(self, state: _PerIPState, now: float):
        # drop old request timestamps
        cutoff = now - self.window
        while state.req_times and state.req_times[0] < cutoff:
            state.req_times.popleft()
        # drop old byte events and keep sum small
        while state.byte_events and state.byte_events[0][0] < cutoff:
            state.byte_events.popleft()

    def _bytes_in_window(self, state: _PerIPState) -> int:
        return sum(n for (_, n) in state.byte_events)

    def check(self, addr: str, filesize: int, flags: Any = None) -> Tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str). If allowed is True, the caller *must*
        call release_after_transfer(ip, bytes_sent) when the transfer finishes (or fails)
        """
        now = time.monotonic()
        ip = _normalize_ip(addr)
        if ip is None:
            return False, "invalid ip format"

        with self._lock:
            state = self._states[ip]

            # banned?
            if state.banned_until > now:
                remaining = int(state.banned_until - now)
                return False, f"temporarily banned (retry after {remaining}s)"

            # cleanup sliding-window data
            self._cleanup(state, now)

            # rate check
            reqs = len(state.req_times)
            if reqs >= self.max_reqs:
                # enforce ban
                state.banned_until = now + self.ban_seconds
                return False, "rate limit exceeded (temporarily banned)"

            # bytes check
            bytes_now = self._bytes_in_window(state)
            if bytes_now + int(filesize) > self.max_bytes:
                return False, "bandwidth quota exceeded for this minute"

            # Passed checks: record request + bytes
            state.req_times.append(now)
            state.byte_events.append((now, int(filesize)))
            return True, ""

    def release_after_transfer(self, addr: str, actual_bytes_sent: int = 0):
        """Call this when a transfer finishes or aborts."""
        now = time.monotonic()
        ip = _normalize_ip(addr)
        if ip is None:
            return
        with self._lock:
            state = self._states.get(ip)
            if not state:
                return

            # Optionally adjust byte_events if you want to replace the speculative size
            # Here we do nothing: bytes already recorded at request time.
            # If you'd rather record actual bytes only, modify logic accordingly.

    def force_unban(self, ip: str):
        with self._lock:
            s = self._states.get(ip)
            if s:
                s.banned_until = 0.0

def _normalize_ip(addr) -> str | None:
    """
    Accept either an IP string ("1.2.3.4") or a tuple (ip, port) produced by sockets.
    Return IP string or None if invalid.
    """
    if addr is None:
        return None
    if isinstance(addr, tuple) and len(addr) >= 1:
        ip = str(addr[0])
    else:
        ip = str(addr)
    # quick sanity check - accept IPv4 dotted decimal for now
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return ip
    # optionally accept hostnames or IPv6 depending on your needs:
    # return ip  # if you want to allow hostnames
    return None

# singleton protector used by your should_receive wrapper
_protector = DDoSProtector()

def should_receive(addr, filesize, flags=None) -> tuple[bool, str]:
    """
    Public wrapper that keeps your requested signature.
    Returns (True, "") when allowed, (False, reason) when blocked.
    """
    if DOSP_ENABLED:
        return _protector.check(addr, filesize, flags)
    else:
        return True, ""