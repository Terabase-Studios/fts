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
        "-log", "--logfile",
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
    cache_parser_add(subparsers, parents)
    try:
        from fts.app.config import PLUGINS_ENABLED
    except:
        pass
    else:
        if PLUGINS_ENABLED:
            plugins_parser_add(subparsers, parents)
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

def cache_parser_add(parser, parents):
    """
    Adds the 'cache' subcommand for managing cache and data cleanup.
    """
    # Main 'cache' parser
    cache_parser = parser.add_parser(
        "cache",
        help="Manage cache and data inside ~/.fts",
        parents=parents
    )

    # Create subparsers under 'cache'
    subparsers = cache_parser.add_subparsers(
        title="subcommands",
        dest="subcommand",
        required=True,
        help="Subcommands for cache management"
    )

    def show_subparser_add(subparser, parents):
        show_parser = subparser.add_parser(
            "show",
            help="Display the cache as a tree with the size and purpose of each file",
            parents=parents
        )

        show_parser.add_argument("-y", "--yes", action="store_true", help="force command and ignore all warnings",)


    def backup_subparser_add(subparser, parents):
        backup_parser = subparser.add_parser(
            "backup",
            help="Save a copy of the current cache",
            parents=parents
        )

        backup_parser.add_argument("-y", "--yes", action="store_true", help="force command and ignore all warnings",)


    def restore_subparser_add(subparser, parents):
        restore_parser = subparser.add_parser(
            "restore",
            help="Restore the cache to the last backup",
            parents=parents
        )

        restore_parser.add_argument("-y", "--yes", action="store_true", help="force command and ignore all warnings",)


    def clean_subparser_add(subparser, parents):
        clean_parser = subparser.add_parser(
            "clean",
            help="Perform cache cleanup at various levels",
            parents=parents
        )

        clean_parser.add_argument("-y", "--yes", action="store_true", help="force command and ignore all warnings",)

        clean_parser.add_argument(
            "-l",
            "--level",
            choices=["clean", "clear", "reset", "purge"],
            default="clean",
            help=(
                "Specifies cleanup depth (default: clean):\n"
                "  clean - Remove chats, seen IPs, transfer logs.\n"
                "  clear - Also remove debug logs, contacts, muted users.\n"
                "  reset - Also remove configuration files, seen fingerprints, aliases, and the plugin dir.\n"
                "  purge - Delete the entire ~/.fts directory."
            )
        )

    show_subparser_add(subparsers, parents)
    backup_subparser_add(subparsers, parents)
    restore_subparser_add(subparsers, parents)
    clean_subparser_add(subparsers, parents)

def plugins_parser_add(parser, parents):
    """
    Adds the 'cache' subcommand for managing cache and data cleanup.
    """
    # Main 'cache' parser
    cache_parser = parser.add_parser(
        "plugins",
        help="Manage TUI plugins",
        parents=parents
    )

    # Create subparsers under 'cache'
    subparsers = cache_parser.add_subparsers(
        title="subcommands",
        dest="subcommand",
        required=True,
        help="Subcommands for cache management"
    )

    def show_subparser_add(subparser, parents):
        show_parser = subparser.add_parser(
            "show",
            help="Display a list of available plugins to install",
            parents=parents
        )

        show_parser.add_argument("-p", "--plugin", type=str, help="show detailed information on an installed plugin",)

    def install_subparser_install(subparser, parents):
        install_parser = subparser.add_parser(
            "install",
            help="Install or update a plugin",
            parents=parents
        )

        install_parser.add_argument("plugin", type=str, nargs='+', help="plugin to install, use all for all plugins",)

    def upgrade_subparser_install(subparser, parents):
        upgrade_parser = subparser.add_parser(
            "upgrade",
            help="Update all installed plugins",
            parents=parents
        )

        upgrade_parser.add_argument("-f", "--force", action="store_true", help="reinstall all installed plugins",)

    def uninstall_subparser_install(subparser, parents):
        uninstall_parser = subparser.add_parser(
            "uninstall",
            help="Uninstall a plugin",
            parents=parents
        )

        uninstall_parser.add_argument("plugin", type=str, nargs='+', help="plugin to install",)
        uninstall_parser.add_argument("-a", "--all", action="store_true", help="uninstall plugin generated files in the cache, use all for all plugins",)


    show_subparser_add(subparsers, parents)
    install_subparser_install(subparsers, parents)
    upgrade_subparser_install(subparsers, parents)
    uninstall_subparser_install(subparsers, parents)