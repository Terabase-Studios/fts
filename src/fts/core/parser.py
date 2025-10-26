import argparse
import pathlib


def create_parser() -> argparse.ArgumentParser:
    # --- Create a parent parser just for logging options ---
    log_parent = argparse.ArgumentParser(add_help=False)
    group = log_parent.add_mutually_exclusive_group()
    group.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="suppress non-critical output"
    )
    group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="enable verbose debug output"
    )
    log_parent.add_argument(
        "--logfile",
        type=pathlib.Path,
        help="log output to a file",
    )

    # --- Root parser ---
    parser = argparse.ArgumentParser(
        prog="fts",
        description="FTS: File transfers! =)",
        parents=[log_parent],
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="COMMAND",
        help="available commands:",
    )

    # --- Add command flags ---
    parents = [log_parent]
    open_parser_add(subparsers, parents)
    send_parser_add(subparsers, parents)
    close_parser_add(subparsers, parents)
    trust_parser_add(subparsers, parents)
    alias_parser_add(subparsers, parents)
    return parser


def open_parser_add(parser, parents):
    open_parser = parser.add_parser("open", help="start a server and listen for incoming transfers", parents=parents)
    open_parser.add_argument("output", type=pathlib.Path, metavar="OUTPUT_PATH", nargs="?", help="directory to save incoming transfers")
    open_parser.add_argument("-d", "--detached", action="store_true", help="run server in the background",)
    open_parser.add_argument("--progress", action="store_true", help="show progress bar for incoming transfers")
    open_parser.add_argument("--unprotected", action="store_true", help="disable file request verification",)
    open_parser.add_argument("-l", "--limit", type=str, metavar="SIZE", help="max recieving speed (e.g. 500KB, 2MB, 1GB)")
    open_parser.add_argument("-p", "--port", type=int, metavar="PORT", help="override port used")
    open_parser.add_argument("--ip", type=str, help="only listen to file transfers from this IP")
    open_parser.add_argument("-c", "--max-concurrent-transfers", dest="max_transfers", type=int, help="Maximum transfers running at once")
    open_parser.add_argument("-m", "--max-transfers", dest="max_sends", type=int, help="Maximum total amount of transfers")

def send_parser_add(parser, parents):
    send_parser = parser.add_parser("send", help="connect to the target server and transfer the file", parents=parents)
    send_parser.add_argument("path", type=pathlib.Path, help="path to the file being sent")
    send_parser.add_argument("ip", type=str, help="server IP to send to")
    send_parser.add_argument("-n", "--name", type=str, help="send file with this name")
    send_parser.add_argument("-p", "--port", type=int, help="override port used (change to port an open server is running on)")
    send_parser.add_argument("-l", "--limit", type=str, help="max sending speed (e.g. 500KB, 2MB, 1GB)")
    send_parser.add_argument("--nocompress", action="store_true", help="Skip compression (use if fts is compressing an already compressed file)")
    send_parser.add_argument("--progress", action="store_true", help="show progress bar for the transfer")

def close_parser_add(parser, parents):
    close_parser = parser.add_parser( "close", help="close a detached server", parents=parents)

def trust_parser_add(parser, parents):
    trust_parser = parser.add_parser("trust", help="allow a new certificate to be trusted if changed", parents=parents)
    trust_parser.add_argument( "ip", type=str, help="IP address whose certificate should be trusted")

def alias_parser_add(parser, parents):
    alias_parser = parser.add_parser("alias", help="manage aliases", parents=parents)
    alias_parser.add_argument("action", choices=["add", "remove", "list"], help="action to perform")
    alias_parser.add_argument("name", nargs="?", type=str, help="alias typed name (required for 'add/remove')")
    alias_parser.add_argument("value", nargs="?", type=str, help="alias true value (required for 'add')")
    alias_parser.add_argument("type", nargs="?", type=str, choices=["ip", "dir"],
                              help="type of alias (required for 'add/remove')")
    alias_parser.add_argument("-y", "--yes", action="store_true", help="force command and ignore all warnings",)