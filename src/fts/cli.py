#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
import argparse
import os
import sys
import pathlib

import argcomplete

from fts.core.aliases import resolve_alias, _load_aliases


# --- Alias Arg Completion ---
def dir_alias_completer(prefix, parsed_args, **kwargs):
    """Suggest directory aliases that start with the given prefix."""
    aliases = _load_aliases(logger=None)
    return [a for a in aliases.get("dir", []) if a.startswith(prefix)]

def ip_alias_completer(prefix, parsed_args, **kwargs):
    """Suggest IP aliases that start with the given prefix."""
    aliases = _load_aliases(logger=None)
    return [a for a in aliases.get("ip", []) if a.startswith(prefix)]

# --- Logger setup ---
try:
    from fts.core.logger import setup_logging
except ImportError:
    import logging

    def setup_logging(verbose=False, quiet=False, logfile=None):
        """Fallback logger if fts.core.logger is unavailable."""
        logger = logging.getLogger("fts")
        logger.handlers.clear()

        level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO
        logger.setLevel(level)

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(fmt)
        logger.addHandler(console)

        if logfile:
            file_handler = logging.FileHandler(logfile, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)

        return logger

# --- Reusable argument groups ---
def add_common_flags(parser, no_progress=False):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-q", "--quiet", action="store_true", help="suppress output")
    group.add_argument("-v", "--verbose", action="store_true", help="enable verbose output")

    if not no_progress:
        parser.add_argument("--progress", action="store_true", help="show progress")
    parser.add_argument("--logfile", metavar="FILE", type=str, help="log output to a file").completer = dir_alias_completer

def add_network_flags(parser):
    parser.add_argument("-p", "--port", type=int, help="port number to use")
    parser.add_argument("--ip", metavar="ADDR", help="IP address to connect to").completer = ip_alias_completer

# --- Lazy command loader with caching ---
_command_cache = {}

def load_cmd(module_path, func_name):
    """Lazy loader for commands, imports on first use and caches the function."""
    def wrapper(args, logger):
        key = (module_path, func_name)
        if key not in _command_cache:
            try:
                mod = __import__(module_path, fromlist=[func_name])
                _command_cache[key] = getattr(mod, func_name)
            except (ImportError, AttributeError) as e:
                logger.error(
                    "Failed to load command. Your install may be corrupted.\n"
                    "Run 'fts update --repair' or reinstall.\n"
                    f"{e}"
                )
                sys.exit(1)
        return _command_cache[key](args, logger)
    return wrapper

# --- Main CLI setup ---
def main():
    parser = argparse.ArgumentParser(prog="fts", description="File transferring, chatroom's, and more!")
    subparsers = parser.add_subparsers(dest="command")

    # Enable tab completion
    argcomplete.autocomplete(parser)

    # --- open ---
    open_parser = subparsers.add_parser("open", aliases=["o", "listen"], help="start a server and listen for transfers")
    open_parser.add_argument("-d", "--detached", action="store_true", help="run server in the background")
    open_parser.add_argument("-o", "--output", type=pathlib.Path, metavar="OUTPUT_PATH", help="where to save incoming transfers").completer = dir_alias_completer
    open_parser.add_argument("-l", "--limit", type=str, help="sending limit (B KB MB GB TB PB)")
    open_parser.add_argument("-t", "--timeout", type=int, help="time to wait for connection")
    open_parser.add_argument("-x", "--extract", action="store_true", help="auto-extract transferred directories")
    add_common_flags(open_parser)
    add_network_flags(open_parser)
    open_parser.set_defaults(func=load_cmd("fts.commands.server", "cmd_open"))

    # --- send ---
    send_parser = subparsers.add_parser("send", aliases=["s"], help="send a file")
    send_parser.add_argument("path", help="file to send").completer = dir_alias_completer
    send_parser.add_argument("ip", help="target IP address").completer = ip_alias_completer
    send_parser.add_argument("-n", "--name", type=str, help="name to send file as")
    send_parser.add_argument("-p", "--port", type=int, help="port number to use")
    send_parser.add_argument("-l", "--limit", type=str, help="sending limit (B KB MB GB TB PB)")
    send_parser.add_argument("--nocompress", action="store_true", help="skip compression (can be faster)")
    add_common_flags(send_parser)
    send_parser.set_defaults(func=load_cmd("fts.commands.sender", "cmd_send"))

    # --- send-dir ---
    send_dir_parser = subparsers.add_parser("send-dir", aliases=["sd", "dir"], help="send a directory")
    send_dir_parser.add_argument("path", type=pathlib.Path, help="directory to send").completer = dir_alias_completer
    send_dir_parser.add_argument("ip", help="target IP address").completer = ip_alias_completer
    send_dir_parser.add_argument("-n", "--name", type=str,  help="name to send dir as")
    send_dir_parser.add_argument("-p", "--port", type=int, help="port number to use")
    send_dir_parser.add_argument("-l", "--limit", type=int, help="sending limit (B KB MB GB TB PB)")
    send_dir_parser.add_argument("--pyzip", action="store_true", help="use Python for compression")
    add_common_flags(send_dir_parser)
    send_dir_parser.set_defaults(func=load_cmd("fts.commands.sender", "cmd_send_dir"))

    # --- close ---
    close_parser = subparsers.add_parser("close", aliases=["c", "stop"], help="close detached server")
    add_common_flags(close_parser, no_progress=True)
    close_parser.set_defaults(func=load_cmd("fts.commands.server", "cmd_close"))

    # --- update ---
    update_parser = subparsers.add_parser("update", aliases=["u", "upgrade"], help="update to the newest version")
    update_parser.add_argument("-r", "--repair", action="store_true", help="force update")
    add_common_flags(update_parser)
    update_parser.set_defaults(func=load_cmd("fts.commands.updater", "cmd_update"))

    # --- version ---
    version_parser = subparsers.add_parser("version", aliases=["v"], help="show version information")
    version_parser.set_defaults(func=load_cmd("fts.commands.misc", "cmd_version"))

    # --- trust ---
    trust_parser = subparsers.add_parser("trust", aliases=["allow"], help="trust an IP certificate")
    trust_parser.add_argument("ip", help="IP address to trust").completer = ip_alias_completer
    trust_parser.set_defaults(func=load_cmd("fts.core.secure", "cmd_clear_fingerprint"))

    # --- chat ---
    chat_parser = subparsers.add_parser("chat", aliases=["talk"], help="create or join a chatroom")
    chat_subparsers = chat_parser.add_subparsers(dest="action", required=True, help="action to perform")

    # chat create
    create_parser = chat_subparsers.add_parser("create", help="create a new chatroom")
    create_parser.add_argument("name", type=str, help="your username")
    create_parser.add_argument("-p", "--port", type=int, help="port number to use")
    create_parser.set_defaults(func=load_cmd("fts.commands.chat", "cmd_chat"))

    # chat join
    join_parser = chat_subparsers.add_parser("join", help="join an existing chatroom")
    join_parser.add_argument("ip", type=str, help="IP to join")
    join_parser.add_argument("name", type=str, help="your username")
    join_parser.add_argument("-p", "--port", type=int, help="port number to use")
    join_parser.set_defaults(func=load_cmd("fts.commands.chat", "cmd_chat"))

    # --- alias ---
    alias_parser = subparsers.add_parser("alias", aliases=["a"], help="manage aliases")
    alias_parser.add_argument("action", choices=["add", "remove", "list"], help="action to perform")
    alias_parser.add_argument("name", nargs="?", type=str, help="alias name (required for 'add/remove')")
    alias_parser.add_argument("value", nargs="?", type=str, help="alias value (required for 'add')")
    alias_parser.add_argument("type", nargs="?", type=str, choices=["ip", "dir"], help="type of alias (required for 'add')")
    alias_parser.set_defaults(func=load_cmd("fts.core.aliases", "cmd_alias"))

    # --- Parse arguments ---
    args = parser.parse_args()
    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)


    # Enforce alias 'add' requires type
    if args.command in ("alias", "a") and args.action == "add" and not args.type:
        print("Error: 'alias add' requires a type argument ('ip' or 'dir').\n")
        sys.exit(2)

    # --- Setup logger ---
    logfile = getattr(args, "logfile", None)
    log_created = False
    if logfile:
        logfile = resolve_alias(logfile, "dir", logger=None)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(logfile)), exist_ok=True)
            if not os.path.exists(logfile):
                open(logfile, "a").close()
                log_created = True
        except Exception as e:
            print(f"Warning: Could not create logfile '{logfile}': {e}")
            logfile = None

    # Determine logging mode based on command
    if args.command == "chat":
        log_mode = "ptk"  # Use prompt_toolkit mode for chat
    else:
        log_mode = "tqdm"  # Default tqdm-compatible mode

    logger = setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
        logfile=logfile,
        mode=log_mode,
    )
    if log_created:
        logger.info(f"Log file created: {logfile}")

    # --- Resolve aliases ---
    if getattr(args, "output", None):
        args.output = resolve_alias(args.output, "dir", logger=logger)
    if getattr(args, "path", None):
        args.path = resolve_alias(args.path, "dir", logger=logger)
    if getattr(args, "ip", None):
        args.ip = resolve_alias(args.ip, "ip", logger=logger)

    # --- Run selected command ---
    args.func(args, logger)
    print('')

if __name__ == "__main__":
    main()
