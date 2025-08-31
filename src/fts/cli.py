#!/usr/bin/env python3
import argparse
import sys

# --- Logger setup ---
try:
    from .logger import setup_logging
except ImportError:
    # Fallback if logger fails
    import logging

    def setup_logging(verbose=False, quiet=False, logfile=None):
        """
        Fallback logger if the main logger fails to import.
        Prints to console and optionally writes to a file.
        """
        logger = logging.getLogger("fts")
        logger.handlers.clear()

        # Determine log level
        if verbose:
            level = logging.DEBUG
        elif quiet:
            level = logging.WARNING
        else:
            level = logging.INFO

        logger.setLevel(level)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # Optional file handler
        if logfile:
            file_handler = logging.FileHandler(logfile, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(console_formatter)
            logger.addHandler(file_handler)

        return logger

# --- Reusable argument groups ---
def add_common_flags(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-q", "--quiet", action="store_true", help="suppress output")
    group.add_argument("-v", "--verbose", action="store_true", help="enable verbose output")

    parser.add_argument("--progress", action="store_true", help="show progress")
    parser.add_argument("--logfile", metavar="FILE", help="log output to a file")


def add_network_flags(parser):
    parser.add_argument("-p", "--port", type=int, help="port number to use")
    parser.add_argument("--ip", metavar="ADDR", help="restrict to this IP address")


# --- Lazy command loader with caching ---
_command_cache = {}

def load_cmd(module_path, func_name):
    """
    Returns a wrapper function that imports the module only when
    the command is executed. Caches the function for repeated calls.
    """
    def wrapper(args, logger):
        key = (module_path, func_name)
        if key not in _command_cache:
            try:
                mod = __import__(module_path, fromlist=[func_name])
                _command_cache[key] = getattr(mod, func_name)
            except (ImportError, AttributeError) as e:
                logger.error(
                    "Failed to load command, your install may be corrupted. "
                    "\nRun 'fts update --repair' or reinstall."
                    f"\n{e}"
                )
                sys.exit(1)
        return _command_cache[key](args, logger)
    return wrapper


# --- Main CLI setup ---
def main():
    parser = argparse.ArgumentParser(prog="fts", description="Fake Tool Suite CLI")
    subparsers = parser.add_subparsers(dest="command")

    # --- open ---
    open_parser = subparsers.add_parser(
        "open", aliases=["o", "listen"], help="start a server and listen for transfers"
    )
    open_parser.add_argument("-d", "--detached", action="store_true", help="run server in the background")
    open_parser.add_argument("-o", "--output", metavar="OUTPUT_PATH", help="where to save incoming file transfers")
    open_parser.add_argument("-t", "--timeout", type=int, help="operation timeout in seconds")
    open_parser.add_argument("-x", "--extract", action="store_true", help="auto-extract transferred directories")
    add_common_flags(open_parser)
    add_network_flags(open_parser)
    open_parser.set_defaults(func=load_cmd("fts.server", "cmd_open"))

    # --- send ---
    send_parser = subparsers.add_parser("send", aliases=["s"], help="send file to target")
    send_parser.add_argument("path", help="path of file to send")
    send_parser.add_argument("ip", help="target IP address")
    send_parser.add_argument("-n", "--name", help="name to send file as")
    add_common_flags(send_parser)
    add_network_flags(send_parser)
    send_parser.set_defaults(func=load_cmd("fts.sender", "cmd_send"))

    # --- send-dir ---
    send_dir_parser = subparsers.add_parser("send-dir", aliases=["sd", "dir"], help="send directory to target")
    send_dir_parser.add_argument("path", help="path of directory to send")
    send_dir_parser.add_argument("ip", help="target IP address")
    send_dir_parser.add_argument("-n", "--name", help="name to send dir as")
    send_dir_parser.add_argument("--py-zip", action="store_true", help="use python when compressing")
    add_common_flags(send_dir_parser)
    add_network_flags(send_dir_parser)
    send_dir_parser.set_defaults(func=load_cmd("fts.sender", "cmd_send_dir"))

    # --- close ---
    close_parser = subparsers.add_parser("close", aliases=["c", "stop"], help="close detached server")
    add_common_flags(close_parser)
    close_parser.set_defaults(func=load_cmd("fts.server", "cmd_close"))

    # --- update ---
    update_parser = subparsers.add_parser("update", aliases=["u", "upgrade"], help="update to the newest version")
    update_parser.add_argument("-r", "--repair", action="store_true", help="force update")
    add_common_flags(update_parser)
    update_parser.set_defaults(func=load_cmd("fts.updater", "cmd_update"))

    # --- version ---
    version_parser = subparsers.add_parser("version", aliases=["v"], help="show version information")
    version_parser.set_defaults(func=load_cmd("fts.commands", "cmd_version"))

    # --- trust ---
    trust_parser = subparsers.add_parser("trust", aliases=["allow"], help="allow a new certificate to be registered to this IP")
    trust_parser.add_argument("ip", help="IP address to trust")
    trust_parser.set_defaults(func=load_cmd("fts.secure", "cmd_clear_fingerprint"))

    # --- Parse arguments ---
    args = parser.parse_args()
    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # --- Setup logger ---
    logger = setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
        logfile=getattr(args, "logfile", None),
    )

    # --- Run the selected command ---
    args.func(args, logger)


if __name__ == "__main__":
    main()
