"""
FTS Chat Meter Plugin

Description:
This plugin protects your FTS chat from flooding or spam by rate-limiting messages per IP.
It uses a token bucket system to allow bursts but prevent sustained message spam.

How it works:
- Each IP has its own token bucket.
- By default, each IP can send up to 5 messages and refills 1 token per second.
- If an IP uses all its tokens, all other messages are blocked until tokens refill.
- A message in chat is printed when an ip is restricted

Why use it:
- Prevents chat spamming or accidental flooding.
- Works automatically per-IP, no configuration needed.

Usage:
- Place this plugin in your FTS plugin directory.
"""

import time
import functools
import types
from typing import Callable
from collections import defaultdict
from fts.app.backend.contacts import replace_with_contact
import fts.app.frontend.chat as chat
from textual.widgets import RichLog

PLUGIN_NAME = "ChatMeter"

def copy_func(f: Callable) -> Callable:
    g = types.FunctionType(
        f.__code__,
        f.__globals__,
        name=f.__name__,
        argdefs=f.__defaults__,
        closure=f.__closure__
    )
    g = functools.update_wrapper(g, f)
    g.__kwdefaults__ = getattr(f, "__kwdefaults__", None)
    return g

class TokenBucket:
    def __init__(self, max_tokens=5, refill_rate=1):
        """
        max_tokens: maximum burst allowed
        refill_rate: tokens added per second
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.tokens = max_tokens
        self.last_check = time.time()
        self.warned = False

    def consume(self, amount=1):
        now = time.time()
        # Refill tokens based on elapsed time
        delta = now - self.last_check
        self.tokens += delta * self.refill_rate
        if self.tokens > self.max_tokens:
            self.tokens = self.max_tokens
            self.warned = False
        self.last_check = now

        if self.tokens >= amount:
            self.tokens -= amount
            return True, False
        else:
            warned = self.warned
            self.warned = True
            return False, not warned


# Dictionary to store buckets per IP
buckets = defaultdict(TokenBucket)
original_on_udp_message = None


def approve(ip: str) -> (bool, bool):
    """
    Returns True if this IP is allowed to send a message.
    Returns False if it is over the rate limit.
    """
    bucket = buckets[ip]  # will create a new bucket automatically if missing
    return bucket.consume()


def on_udp_message(self, data: bytes, addr):
    global original_on_udp_message
    sender = replace_with_contact(addr[0])
    approved, warn = approve(addr[0])
    if approved:
        original_on_udp_message(self, data, addr)
    else:
        if not warn:
            return
        user_color = self.color_for_sender(sender)
        color = self.color_for_sender(PLUGIN_NAME)
        line = f"[bold {color}]{PLUGIN_NAME}:[/bold {color}] User [bold {user_color}]{sender}[/bold {user_color}]: messages are metered"
        log = self.query_one(RichLog)
        log.write(line)

def setup_plugin():
    global original_on_udp_message
    original_on_udp_message = copy_func(chat.Chat.on_udp_message)
    chat.Chat.on_udp_message = on_udp_message