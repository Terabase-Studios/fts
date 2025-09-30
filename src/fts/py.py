from argparse import Namespace
from fts.commands.sender import cmd_send
from fts.commands.server import cmd_open
from fts.core.aliases import resolve_args, load_aliases, cmd_alias
from fts.core.detatched import cmd_close
from fts.core.logger import setup_logging
import asyncio

from fts.core.secure import cmd_clear_fingerprint

logger = setup_logging()


def send(path: str, ip: str, port: int = -1, limit: int | str = 0, progress: bool = False, name: str = None, compress: bool = True):
    args = Namespace(
        path = path,
        ip = ip,
        limit = limit,
        port = 0 if port == -1 else port,
        progress = progress,
        name = name,
        nocompress = not compress,
    )

    cmd_send(resolve_args(args, logger), logger)


def open(path: str, ip: str = None, port: int = -1, limit: int | str = 0, progress: bool = False, protected: bool = True, max_concurrent_transfers: int = 0):
    args = Namespace(
        output = path,
        ip = ip,
        port = 0 if port == -1 else port,
        limit = limit,
        progress = progress,
        unprotected = not protected,
        max_transfers = max_concurrent_transfers,
    )

    cmd_open(resolve_args(args, logger), logger)


def close():
    args = Namespace()
    cmd_close(args, logger)


def trust(ip):
    args = Namespace(
        ip = ip,
    )

    cmd_clear_fingerprint(resolve_args(args, logger), logger)


def get_aliases():
    return load_aliases()


def add_alias(name: str, value: str, type: str):
    args = Namespace(
        action = "add",
        name = name,
        value = value,
        type = type,
        yes = True
    )
    cmd_alias(args, logger)


def remove_alias(name: str, type: str):
    args = Namespace(
        action = "remove",
        name = name,
        type = type,
        value = None
    )
    cmd_alias(args, logger)