import sys
from argparse import Namespace

from fts.commands.sender import cmd_send
from fts.commands.server import cmd_open
from fts.core.aliases import resolve_args, load_aliases, cmd_alias
from fts.core.detatched import cmd_close
from fts.core.logger import setup_logging
from fts.core.secure import cmd_clear_fingerprint, is_public_network
from fts.manager import Manager

logger = setup_logging()

def _get_logger(base_logger, id: str):
    if isinstance(base_logger, str):
        # Treat it as a logfile path
        return setup_logging(logfile=base_logger, id=id)
    elif base_logger is None:
        # Default logger
        return setup_logging(id=id)
    else:
        # Already a logger object
        return base_logger


def send(path: str, ip: str, port: int = -1, limit: int | str = 0, progress: bool = False, name: str = None, compress: bool = True, manager: Manager = None):
    args = Namespace(
        path = path,
        ip = ip,
        limit = limit,
        port = 0 if port == -1 else port,
        progress = progress,
        name = name,
        nocompress = not compress,
    )

    func_logger = _get_logger(logger, "send")
    cmd_send(resolve_args(args, func_logger), func_logger, manager=manager)


def open(path: str, ip: str = None, port: int = -1, limit: int | str = 0, progress: bool = False, protected: bool = True, max_concurrent_transfers: int = 0, manager: Manager = None, max_transfers: int = None):
    args = Namespace(
        output = path,
        ip = ip,
        port = 0 if port == -1 else port,
        limit = limit,
        progress = progress,
        unprotected = not protected,
        max_transfers = max_concurrent_transfers,
        max_sends=max_transfers,
    )

    func_logger = _get_logger(logger, "open")
    cmd_open(resolve_args(args, func_logger), func_logger, manager=manager)


def close():
    args = Namespace()
    func_logger = _get_logger(logger, "close")
    cmd_close(args, func_logger)


def trust(ip):
    args = Namespace(
        ip = ip,
    )

    func_logger = _get_logger(logger, "trust")
    cmd_clear_fingerprint(resolve_args(args, func_logger), func_logger)


def get_aliases():
    return load_aliases()


def add_alias(name: str, value: str, alias_type: str):
    args = Namespace(
        action = "add",
        name = name,
        value = value,
        type = alias_type,
        yes = True
    )

    func_logger = _get_logger(logger, "alias")

    cmd_alias(args, func_logger)


def remove_alias(name: str, alias_type: str):
    args = Namespace(
        action = "remove",
        name = name,
        type = alias_type,
        value = None
    )

    func_logger = _get_logger(logger, "alias")
    cmd_alias(args, func_logger)

if is_public_network("-v" in sys.argv or "--verbose" in sys.argv):
    logger.critical('FTS is disabled on public network\n')
    sys.exit(0)