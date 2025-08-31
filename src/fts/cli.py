#!/usr/bin/env python3
import argparse
import sys
import logging


# --- Logging setup ---
def setup_logging(verbose=False, quiet=False, logfile=None):
    """Configure logger for CLI commands."""
    logger = logging.getLogger("fts")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Determine logging level
    if quiet:
        logger.setLevel(logging.ERROR)
    elif verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Optional file logging
    if logfile:
        file_handler = logging.FileHandler(logfile)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# --- Reusable argument groups ---
def add_common_flags(p):
    """Flags that make sense for most commands"""
    group = p.add_mutually_exclusive_group()
    group.add_argument("-q", "--quiet", action="store_true", help="suppress output")
    group.add_argument("-v", "--verbose", action="store_true", help="enable verbose output")

    p.add_argument("--progress", action="store_true", help="show progress")
    p.add_argument("--logfile", metavar="FILE", help="log output to a file")


def add_network_flags(p):
    """Flags for network operations"""
    p.add_argument("-p", "--port", type=int, help="port number to use")
    p.add_argument("--ip", metavar="ADDR", help="restrict to this IP address")


def main():
    parser = argparse.ArgumentParser(prog="fts", description="Fake Tool Suite CLI")
    subparsers = parser.add_subparsers(dest="command")

    # --- open ---
    open_parser = subparsers.add_parser("open", help="start a server and listen for transfers")
    open_parser.add_argument("-d", "--detached", action="store_true", help="run server in the background")
    open_parser.add_argument("-o", "--output", metavar="OUTPUT_PATH", help="where to save incoming file transfers")
    open_parser.add_argument("-t", "--timeout", type=int, help="operation timeout in seconds")
    open_parser.add_argument("-x", "--extract", action="store_true", help="auto-extract transferred directories")
    add_common_flags(open_parser)
    add_network_flags(open_parser)
    open_parser.set_defaults(func=lambda args, logger: __import__('fts.server').server.cmd_open(args, logger))

    # --- send ---
    send_parser = subparsers.add_parser("send", help="send file to target")
    send_parser.add_argument("path", help="path of file to send")
    send_parser.add_argument("ip", help="target IP address")
    send_parser.add_argument("-n", "--name", help="name to send file as")
    add_common_flags(send_parser)
    add_network_flags(send_parser)
    send_parser.set_defaults(func=lambda args, logger: __import__('fts.sender').sender.cmd_send(args, logger))

    # --- send-dir ---
    send_dir_parser = subparsers.add_parser("send-dir", help="send directory to target")
    send_dir_parser.add_argument("path", help="path of directory to send")
    send_dir_parser.add_argument("ip", help="target IP address")
    send_dir_parser.add_argument("-n", "--name", help="name to send dir as")
    send_dir_parser.add_argument("--py-zip", action="store_true", help="use python when compressing. helpful for large directories when native compression fails")
    add_common_flags(send_dir_parser)
    add_network_flags(send_dir_parser)
    send_dir_parser.set_defaults(func=lambda args, logger: __import__('fts.sender').sender.cmd_send_dir(args, logger))

    # --- close ---
    close_parser = subparsers.add_parser("close", help="close detached server")
    add_common_flags(close_parser)
    open_parser.set_defaults(func=lambda args, logger: __import__('fts.server').server.cmd_close(args, logger))

    # --- update ---
    update_parser = subparsers.add_parser("update", help="update to the newest version")
    update_parser.set_defaults(func=lambda args, logger: __import__('fts.updater').commands.cmd_update(args, logger))

    # --- version ---
    version_parser = subparsers.add_parser("version", help="show version information")
    version_parser.set_defaults(func=lambda args, logger: __import__('fts.commands').commands.cmd_version(args, logger))

    # --- parse args ---
    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)

    # --- Setup logger before running command ---
    logger = setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
        logfile=getattr(args, "logfile", None),
    )

    # --- Call command, passing logger ---
    args.func(args, logger)


if __name__ == "__main__":
    main()
