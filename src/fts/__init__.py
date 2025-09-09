#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
def __version__():
    return "0.5.0"

import os
import sys
import subprocess
import pathlib
from gooey import Gooey, GooeyParser
import fts
import tempfile
import json
import argparse

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
def add_common_flags(parser, *, progress=True, logfile=True):
    """Add common flags shared by most commands."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-q", "--quiet", action="store_true",
                       help="suppress output")
    group.add_argument("-v", "--verbose", action="store_true",
                       help="enable verbose output")

    if progress:
        parser.add_argument("--progress", action="store_true",
                            help="show progress")

    if logfile:
        parser.add_argument("--logfile", metavar="FILE", widget="FileChooser", type=str,
                            help="log output to a file"
                            ).completer = dir_alias_completer


def add_network_flags(parser, *, require_ip=False, default_port=None, have_ip=True):
    """Add network-related options: --ip and --port."""
    parser.add_argument("-p", "--port", type=int, default=default_port,
                        help="override port to connect to")
    if have_ip:
        parser.add_argument("--ip", metavar="address", required=require_ip,
                            help="IP address to connect to"
                            ).completer = ip_alias_completer


def add_transfer_flags(parser, *, allow_name=True, limit_type=str):
    """Flags common to file/directory sending commands."""
    if allow_name:
        parser.add_argument("-n", "--name", type=str,
                            help="override name of file/directory")
    parser.add_argument("-l", "--limit", type=limit_type,
                        help="sending limit (B KB MB GB TB PB)")


def build_parser(gui=False):
    """Return the top-level parser, with Gooey GUI organization."""
    parser = GooeyParser(
        prog="FTS",
        description="File transferring, chatrooms, and more!"
    )

    subparsers = parser.add_subparsers(dest="command")

    # --- open ---
    open_parser = subparsers.add_parser(
        "open", aliases=["o", "listen"], help="start a server and listen for transfers"
    )

    # Required / core
    open_required = open_parser.add_argument_group("Server settings")
    open_required.add_argument(
        "-o", "--output", type=pathlib.Path, widget="DirChooser",
        metavar="output path", help="where to save incoming transfers (only required argument)", required=True
    ).completer = dir_alias_completer
    open_required.add_argument(
        "-t", "--timeout", type=int, help="time to wait for connection"
    )
    if not gui:
        open_required.add_argument(
            "-d", "--detached", action="store_true", help="run server in the background"
        )

    # Transfer options
    transfer_group = open_parser.add_argument_group("Transfer options")
    transfer_group.add_argument(
        "-x", "--extract", action="store_true", help="auto-extract transferred directories"
    )
    add_transfer_flags(transfer_group, allow_name=False)

    # Networking
    net_group = open_parser.add_argument_group("Networking")
    add_network_flags(net_group)

    # Logging
    log_group = open_parser.add_argument_group("Logging")
    add_common_flags(log_group)

    open_parser.set_defaults(func=load_cmd("fts.commands.server", "cmd_open"))

    # --- send ---
    send_parser = subparsers.add_parser("send", aliases=["s"], help="send a file")
    req_group = send_parser.add_argument_group("Required inputs")
    req_group.add_argument("path", widget="FileChooser", help="file to send").completer = dir_alias_completer
    req_group.add_argument("ip", help="target IP address").completer = ip_alias_completer

    options_group = send_parser.add_argument_group("Options")
    options_group.add_argument("--nocompress", metavar="no compress", action="store_true", help="skip compression (can be faster)")
    add_transfer_flags(options_group)
    add_network_flags(options_group)

    log_group = send_parser.add_argument_group("Logging")
    add_common_flags(log_group)

    send_parser.set_defaults(func=load_cmd("fts.commands.sender", "cmd_send"))

    # --- send-dir ---
    send_dir_parser = subparsers.add_parser("send-dir", aliases=["sd", "dir"], help="send a directory")
    req_group = send_dir_parser.add_argument_group("Required inputs")
    req_group.add_argument("path", type=pathlib.Path, widget="DirChooser", help="directory to send"
    ).completer = dir_alias_completer
    req_group.add_argument("ip", help="target IP address").completer = ip_alias_completer

    options_group = send_dir_parser.add_argument_group("Options")
    options_group.add_argument("--pyzip", action="store_true", help="use Python for compression")
    add_transfer_flags(options_group)

    net_group = send_dir_parser.add_argument_group("Networking")
    add_network_flags(net_group, have_ip=False)

    log_group = send_dir_parser.add_argument_group("Logging")
    add_common_flags(log_group)

    send_dir_parser.set_defaults(func=load_cmd("fts.commands.sender", "cmd_send_dir"))

    # --- other commands ---
    close_parser = subparsers.add_parser("close", aliases=["c", "stop"], help="close detached server")
    close_parser.set_defaults(func=load_cmd(f"fts.commands.server", f"cmd_close"))

    update_parser = subparsers.add_parser("update", aliases=["u", "upgrade"], help="update to the newest version")
    update_parser.set_defaults(func=load_cmd(f"fts.commands.updater", f"cmd_update"))

    version_parser = subparsers.add_parser("version", aliases=["v"], help="show version information")
    version_parser.set_defaults(func=load_cmd(f"fts.commands.misc", f"cmd_version"))

    # --- chat (flattened) ---
    chat_parser = subparsers.add_parser("chat", aliases=["talk"], help="Create or join a chatroom")
    chat_group = chat_parser.add_argument_group("Chatroom settings")
    chat_group.add_argument(
        "action", choices=["create", "join"], help="Action to perform", widget="Dropdown"
    )
    chat_group.add_argument("name", type=str, help="Your username", widget="TextField")
    chat_group.add_argument("ip", nargs="?", type=str, help="IP to join (only for join)", widget="TextField", default="")
    chat_group.add_argument("-p", "--port", type=str, help="override port to connect to (only for join)", widget="TextField", default="")
    chat_parser.set_defaults(func=load_cmd("fts.commands.chat", "cmd_chat"))


    # --- alias ---
    alias_parser = subparsers.add_parser("alias", aliases=["a"], help="manage aliases")
    action_group = alias_parser.add_argument_group("Alias management")
    action_group.add_argument("action", choices=["add", "remove", "list"], help="action to perform")
    action_group.add_argument("name", nargs="?", type=str, help="alias name (only for 'add/remove')")
    action_group.add_argument("value", nargs="?", type=str, help="alias value (only for 'add')")
    action_group.add_argument("type", nargs="?", type=str, choices=["ip", "dir"], help="type of alias (only for 'add')")
    alias_parser.set_defaults(func=load_cmd("fts.core.aliases", "cmd_alias"))

    # Add shared Gooey-compatibility args to root and all subparsers
    def add_hidden_args(p):
        existing = {opt for a in p._actions for opt in a.option_strings}

        # Create (or reuse) a hidden group for Gooey-only args
        hidden_group = getattr(p, "_gooey_hidden_group", None)
        if hidden_group is None:
            hidden_group = p.add_argument_group(
                "Hidden Gooey Args",
                gooey_options={'visible': False}
            )
            # stash it so we don’t create duplicates
            p._gooey_hidden_group = hidden_group

        if "--ignore-gooey" not in existing:
            hidden_group.add_argument("--ignore-gooey", action="store_true", help=argparse.SUPPRESS)

        if "--gooey-json" not in existing:
            hidden_group.add_argument("--gooey-json", action="store_true", help=argparse.SUPPRESS)

    # Add to root parser
    add_hidden_args(parser)

    # Add to every subparser
    for name, subparser in subparsers.choices.items():
        add_hidden_args(subparser)

    return parser


def run(args):
    if "--ignore-gooey" in sys.argv:
        def serialize_args(args):
            """Convert argparse.Namespace to a dict with JSON-serializable values."""
            result = {}
            for k, v in vars(args).items():
                if callable(v):
                    # Skip functions like args.func
                    continue
                elif isinstance(v, pathlib.Path):
                    result[k] = str(v)  # convert Path to string
                else:
                    result[k] = v
            return result

        # Write arguments to the temp file passed by parent process
        outfile = os.environ.get("GOOEY_OUT")
        if not outfile:
            print("Missing GOOEY_OUT env variable", file=sys.__stderr__, flush=True)
            print("Gui Closed", file=sys.__stderr__, flush=True)
            sys.exit(1)

        try:
            with open(outfile, "w") as f:
                json.dump(serialize_args(args), f)
                #print("DEBUG: arguments saved to temp file", file=sys.__stderr__, flush=True)
        except Exception as e:
            print(f"Failed to write args: {e}", file=sys.__stderr__, flush=True)
            print("Gui Closed", file=sys.__stderr__, flush=True)
            sys.exit(1)

        return args


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
        log_mode = "ptk"
    else:
        log_mode = "tqdm"

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
    try:
        args.func(args, logger)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Unhandled Exception: {e}")
    print("")


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

# --- Gooey subprocess entry ---
def handle_gooey_json():
    """Run Gooey and dump Namespace as JSON to a temp file, then exit."""
    @Gooey(program_name="FTS")
    def get_args():
        parser = build_parser()  # your parser builder
        print('INFO: Gui Opened')
        print('WARNING: GUI is heavily experimental, use at your own risk.')
        print('WARNING: Background processes are not available from GUI')
        args = parser.parse_args()
        # Other half continues in run for some reason

    get_args()
    sys.exit(0)


# --- Gooey launcher ---
def handle_gooey():
    """Launch Gooey in a subprocess and return argparse.Namespace to parent."""
    tf = tempfile.NamedTemporaryFile(delete=False)
    tf.close()
    env = dict(os.environ)
    env["GOOEY_OUT"] = tf.name

    try:
        # Launch Gooey subprocess
        result = subprocess.run(
            [sys.executable, fts.__file__, "--gooey-json"],
            env=env,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        # Read args back from temp file
        with open(tf.name, "r") as f:
            args_dict = json.load(f)
        if os.path.exists(tf.name):
            os.remove(tf.name)

        # Rebuild Namespace
        args = argparse.Namespace(**args_dict)

        # Reattach 'func' using the parser
        parser = build_parser()
        subparsers_actions = [
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]

        for subparser_action in subparsers_actions:
            for name, subparser in subparser_action.choices.items():
                if getattr(args, "command", None) == name:
                    args.func = subparser.get_default("func")
                    break

        return args

    except subprocess.CalledProcessError as e:
        print("Gooey subprocess failed:", e.stderr, file=sys.stderr)
        if os.path.exists(tf.name):
            os.remove(tf.name)
        sys.exit(1)

    except Exception as e:
        print("Failed to read arguments from Gooey:", e, file=sys.stderr)
        if os.path.exists(tf.name):
            os.remove(tf.name)
        sys.exit(1)


def main():
    if "--gooey-json" in sys.argv:
        sys.argv.remove("--gooey-json")
        if "--ignore-gooey" in sys.argv:
            sys.argv.remove("--ignore-gooey")
        handle_gooey_json()
        return

    use_gui = "--ignore-gooey" not in sys.argv and len(sys.argv) == 1

    # Remove the script name from sys.argv so Gooey doesn't get confused: THIS IS ABSOLUTELY NECESSARY OR GOOEY WILL CRASH
    sys.argv.pop(0)
    sys.argv.insert(0, fts.__file__)

    if use_gui:
        try:
            args = handle_gooey()
        except Exception as e:
            print(f"Failed to get arguments:", e)
            sys.exit(1)
    else:
        parser = build_parser()
        args = parser.parse_args()

    run(args)

if __name__ == "__main__":
    main()

