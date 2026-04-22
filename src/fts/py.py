import sys
from argparse import Namespace

from fts import install_fast_event_loop
from fts.commands.resume import retrieve_incomplete_transfers, filter_in_progress, cmd_resume, remove
from fts.commands.sender import cmd_send
from fts.commands.server import cmd_open
from fts.core.aliases import resolve_args, load_aliases, cmd_alias
from fts.core.detatched import cmd_close
from fts.core.logger import setup_logging
from fts.core.secure import cmd_clear_fingerprint, is_public_network
from fts.manager import Manager


logger = setup_logging()


def _get_logger(base_logger, id: str):
    """
    Resolve or create a logger instance.

    Args:
        base_logger: Either a logger instance, a logfile path (str), or None.
        id (str): Identifier used to tag the logger instance.

    Returns:
        Logger: A configured logger instance.
    """
    if isinstance(base_logger, str):
        return setup_logging(logfile=base_logger, id=id)
    elif base_logger is None:
        return setup_logging(id=id)
    else:
        return base_logger



def install_accelerated_event_loop(debug_prints=False) -> bool:
    """
    Configure asyncio to use uvloop or winloop globally.

    Must be called once at program startup, before any loops are created.

    Returns:
        success: bool
    """
    success = install_fast_event_loop(debug_prints=debug_prints)
    return success


def send(path: str, ip: str, port: int = -1, limit=0, progress: bool = False, name: str = None,
         compress: bool = True, manager: Manager = None):
    """
    Send a file or directory to a remote receiver.

    Args:
        path (str): Path to the file or directory to send.
        ip (str): Target IP address.
        port (int, optional): Target port. Defaults to auto-select if -1.
        limit (int, optional): Bandwidth limit (0 = unlimited).
        progress (bool, optional): Show progress output.
        name (str, optional): Optional override name for the transfer.
        compress (bool, optional): Enable compression.
        manager (Manager, optional): Transfer manager instance.
    """
    args = Namespace(
        path=path,
        ip=ip,
        limit=limit,
        port=0 if port == -1 else port,
        progress=progress,
        name=name,
        nocompress=not compress,
        autotrust=True
    )

    func_logger = _get_logger(logger, "send")
    cmd_send(resolve_args(args, func_logger), func_logger, manager=manager)


def open(path: str, ip: str = None, port: int = -1, limit=0, progress: bool = False,
         protected: bool = True, max_concurrent_transfers: int = 0, manager: Manager = None,
         max_transfers: int = None, allow_resumes: bool = False):
    """
    Start a receiver/server to accept incoming transfers.

    Args:
        path (str): Output directory for received files.
        ip (str, optional): Bind IP address.
        port (int, optional): Port to listen on (-1 for auto).
        limit (int, optional): Bandwidth limit (0 = unlimited).
        progress (bool, optional): Show progress output.
        protected (bool, optional): Require trusted connections.
        max_concurrent_transfers (int, optional): Max simultaneous transfers.
        manager (Manager, optional): Transfer manager instance.
        max_transfers (int, optional): Max send operations.
        allow_resumes (bool, optional): Allow resuming incomplete transfers.
    """
    args = Namespace(
        output=path,
        ip=ip,
        resume=allow_resumes,
        port=0 if port == -1 else port,
        limit=limit,
        progress=progress,
        unprotected=not protected,
        max_transfers=max_concurrent_transfers,
        max_sends=max_transfers,
    )

    func_logger = _get_logger(logger, "open")
    cmd_open(resolve_args(args, func_logger), func_logger, manager=manager)


def get_incomplete_transfers(include_in_progress: bool = False):
    """
    Retrieve stored incomplete transfers.

    Args:
        include_in_progress (bool): If False, filters out actively progressing transfers.

    Returns:
        list: List of transfer metadata dictionaries.
    """
    transfer_list = retrieve_incomplete_transfers()
    if not include_in_progress:
        transfer_list = filter_in_progress(transfer_list)
    return transfer_list


def resume_incomplete_transfer(transfer_id: int, port: int = -1, limit=0,
                               progress: bool = False, manager: Manager = None):
    """
    Resume a previously incomplete transfer.

    Args:
        transfer_id (int): ID of the transfer to resume.
        port (int, optional): Port override (-1 for default).
        limit (int, optional): Bandwidth limit.
        progress (bool, optional): Show progress output.
        manager (Manager, optional): Transfer manager instance.
    """
    args = Namespace(
        subcommand="start",
        id=transfer_id,
        limit=limit,
        port=0 if port == -1 else port,
        progress=progress,
        autotrust=True
    )

    func_logger = _get_logger(logger, "resume")
    cmd_resume(resolve_args(args, func_logger), func_logger, manager=manager)


def remove_incomplete_transfer(transfer_id):
    """
    Remove a stored incomplete transfer record.

    Args:
        transfer_id (int): ID of the transfer to remove.
    """
    args = Namespace(
        id=transfer_id,
    )
    remove(args)


def close():
    """
    Close any running detached FTS processes or servers.
    """
    args = Namespace()
    func_logger = _get_logger(logger, "close")
    cmd_close(args, func_logger)


def trust(ip):
    """
    Trust a remote IP by clearing its fingerprint requirement.

    Args:
        ip (str): IP address to trust.
    """
    args = Namespace(
        ip=ip,
    )

    func_logger = _get_logger(logger, "trust")
    cmd_clear_fingerprint(resolve_args(args, func_logger), func_logger)


def get_aliases():
    """
    Retrieve all configured aliases.

    Returns:
        dict: Alias definitions grouped by type.
    """
    return load_aliases()


def add_alias(name: str, value: str, alias_type: str):
    """
    Add a new alias.

    Args:
        name (str): Alias name.
        value (str): Value the alias resolves to.
        alias_type (str): Type/category of alias.
    """
    args = Namespace(
        action="add",
        name=name,
        value=value,
        type=alias_type,
        yes=True
    )

    func_logger = _get_logger(logger, "alias")
    cmd_alias(args, func_logger)


def remove_alias(name: str, alias_type: str):
    """
    Remove an existing alias.

    Args:
        name (str): Alias name.
        alias_type (str): Type/category of alias.
    """
    args = Namespace(
        action="remove",
        name=name,
        type=alias_type,
        value=None
    )

    func_logger = _get_logger(logger, "alias")
    cmd_alias(args, func_logger)


if is_public_network("-v" in sys.argv or "--verbose" in sys.argv):
    logger.critical('FTS is disabled on public network\n')
    sys.exit(0)
