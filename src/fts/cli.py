#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
import argparse
import io
import os
import pathlib
import random
import string
import sys
from contextlib import redirect_stdout, redirect_stderr

import argui
from argui.types import FileSelectDir

from fts.core.aliases import resolve_alias
from fts.core.logger import setup_logging
from fts.core.secure import is_public_network

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


# --- Reusable argument groups ---
def add_log_flags(parser: argparse.ArgumentParser, defaults) -> None:
    """Add common logging and output flags."""

    parser.add_argument(
        "--logfile",
        metavar="FILE",
        type=pathlib.Path,
        help="Log output to a file",
        default=defaults.get("logfile", None),
    )

    #group = parser.add_mutually_exclusive_group()
    group = parser
    group.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-critical output"
    )
    group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug output"
    )


def add_network_flags(parser: argparse.ArgumentParser, defaults) -> None:
    """Add network-related flags."""
    parser.add_argument(
        "-p", "--port",
        type=int,
        metavar="PORT",
        help="Override port used (0-65535)"
    )
    parser.add_argument(
        "--ip",
        metavar="ADDR",
        type=str,
        help="restrict requests to IP or hostname"
    )


# --- Main parser ---
def create_parser(gui=False) -> argparse.ArgumentParser:
    defaults = {}

    parser = argparse.ArgumentParser(
        prog="fts",
        description="FTS: File transfers, chatrooms, and more."
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="COMMAND",
        help="Available commands",
    )

    add_log_flags(parser, defaults)

    # --- open ---
    open_parser = subparsers.add_parser(
        "open",
        help="Start a server and listen for incoming transfers"
    )
    open_parser.add_argument(
        "output",
        type=FileSelectDir(),
        metavar="OUTPUT_PATH",
        nargs="?",
        help="Directory to save incoming transfers - required",
        default=defaults.get("output", None),
    )
    open_parser.add_argument(
        "-d", "--detached",
        action="store_true",
        help="Run server in the background",
    )
    open_parser.add_argument(
        "--progress",
        action="store_true",
        help="Show progress bars during operations"
    )
    open_parser.add_argument(
        "-l", "--limit",
        type=str,
        metavar="SIZE",
        help="Transfer rate limit (e.g. 500KB, 2MB, 1GB)"
    )
    add_network_flags(open_parser, defaults)
    # --- send ---
    send_parser = subparsers.add_parser(
        "send",
        help="Send a file to a target host"
    )
    send_parser.add_argument(
        "path",
        type=pathlib.Path,
        help="Path to the file to send - required"
    )
    send_parser.add_argument(
        "ip",
        type=str,
        help="Target IP address or hostname - required"
    )
    send_parser.add_argument(
        "-n", "--name",
        type=str,
        help="Name to send file as"
    )
    send_parser.add_argument(
        "-p", "--port",
        type=int,
        help="Override port used"
    )
    send_parser.add_argument(
        "-l", "--limit",
        type=str,
        metavar="SIZE",
        help="Transfer rate limit (e.g. 500KB, 2MB, 1GB)"
    )
    send_parser.add_argument(
        "--nocompress",
        action="store_true",
        help="Skip compression (faster but larger transfer)"
    )
    send_parser.add_argument(
        "--progress",
        action="store_true",
        help="Show progress bars during operations"
    )

    # --- close ---
    close_parser = subparsers.add_parser(
        "close",
        help="Close a detached server",
    )
    close_parser.add_argument("process", choices=["all", "receiving"], help="process to close")
    # --- trust ---
    if not gui:
        # --- version ---
        version_parser = subparsers.add_parser(
            "version",
            help="Show FTS version information"
        )

    trust_parser = subparsers.add_parser(
        "trust",
        help="Trust an IP certificate"
    )
    trust_parser.add_argument(
        "ip",
        type=str,
        help="IP address whose certificate should be trusted - required"
    )

    # --- alias ---
    alias_parser = subparsers.add_parser("alias", help="manage aliases")
    alias_parser.add_argument("action", choices=["add", "remove", "list"], help="action to perform")
    alias_parser.add_argument("name", nargs="?", type=str, help="alias name (required for 'add/remove')")
    alias_parser.add_argument("value", nargs="?", type=str, help="alias value (required for 'add')")
    alias_parser.add_argument("type", nargs="?", type=str, choices=["ip", "dir"],
                              help="type of alias (required for 'add')")
    return parser


def run(args):
    if args.verbose and args.quiet:
        print("ERROR: Verbose cannot be used with quiet!")
        return

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

        except Exception as e:
            print(f"Warning: Could not create id: {e}")

    # Determine logging mode based on command
    if "chat" in args.command:
        log_mode = "ptk"  # Use prompt_toolkit mode for chat
    else:
        log_mode = "tqdm"  # Default tqdm-compatible mode

    logger = setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
        logfile=logfile,
        mode=log_mode,
        id=args.command,
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

    # --- Enforce Alias ---
    #if "alias" in args.command and args.action == "add" and not args.type:
    #    logger.error("'alias add' requires a type argument ('ip' or 'dir').\n")
    #    sys.exit(2)
    #if "alias" in args.command and (args.action == "add" or args.action == "remove") and not args.name:
    #    logger.error("'alias add/remove' requires a name argument.\n")
    #    sys.exit(2)

    # --- Run selected command ---
    try:
        args.func(args, logger)
    except KeyboardInterrupt:
        pass
    except Exception:
        pass
    print('')

def ensure_func(args):
    if hasattr(args, "func"):
        return args
    # map command -> (module, func_name)
    mapping = {
        "open": ("fts.commands.server", "cmd_open"),
        "send": ("fts.commands.sender", "cmd_send"),
        "close": ("fts.core.detatched", "cmd_close"),
        "version": ("fts.commands.misc", "cmd_version"),
        "trust": ("fts.core.secure", "cmd_clear_fingerprint"),
        "alias": ("fts.core.aliases", "cmd_alias"),
    }

    if args.command in mapping:
        mod, fn = mapping[args.command]
        args.func = load_cmd(mod, fn)

    return args


# Dummy sys.exit to prevent process termination
def dummy_exit(code=0):
    raise RuntimeError(f"sys.exit({code}) called")


# --- Main CLI setup ---
def main():
    if is_public_network("-v" in sys.argv or "--verbose" in sys.argv):
        print('FTS is disabled on public network\n')
        sys.exit(0)
    args = None

    try:
        parser = create_parser()
        args = parser.parse_args()
    except SystemExit:
        pass

    if not args:
        print('')
        return

    try:
        run(ensure_func(args))
    except Exception as e:
        print(f"failed to run command: {e}")

if __name__ == "__main__":
    main()
