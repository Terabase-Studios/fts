import argparse
import asyncio
import json
import os
import socket
import sys

import fts.commands.server as file_server
import fts.library.discovery as discover
from fts.config import LIBRARY_FILE, LIBRARY_PID
from fts.core.aliases import reverse_resolve_alias
from fts.core.detatched import start_detached
from fts.core.secure import is_public_network
from fts.library.map import LibraryMap
from fts.library.map_manager import browse_map
from fts.library.tree_manager import browse_library


def cmd_library(args, logger):
    logger.debug(f"Options: {args}")
    if args.task == "find":
        cmd_find(args, logger)

    elif args.task == "open":
        cmd_open(args, logger)

    elif args.task == "manage":
        cmd_manage(args, logger)


def cmd_find(args, logger):
    """Run discovery and print all responding servers."""
    if is_public_network():
        logger.error("FTS is disabled on public network\n")
        sys.exit(0)

    if not args.output:
        logger.error("No path given")
        return

    output_dir = os.path.abspath(args.output or ".")
    os.makedirs(output_dir, exist_ok=True)

    async def run(args):
        logger.info("Discovering libraries...")
        try:
            servers = await discover.discover_libraries(logger)
        except Exception as e:
            logger.error(f"Failed to discover libraries: {e}")
            return None

        if servers:
            file_selected = False
            lib_file_path = None
            ip = "0.0.0.0"
            # noinspection GrazieInspection
            while not file_selected:
                logger.info("Discovered libraries:")
                index = 1
                ip_list = []
                for ip in servers:
                    logger.info(f"  {index} - {reverse_resolve_alias(ip, "ip")}")
                    ip_list.append(ip)
                    index += 1

                valid_response = False
                library = 0
                print('')

                while not valid_response:
                    try:
                        library = int(input("Please input library number to explore: "))
                        if library < 0 or library > len(servers):
                            raise ValueError
                        valid_response = True
                    except ValueError:
                        logger.error("Please input a valid library number.")

                selected_ip = ip_list[library - 1]
                ip_name = reverse_resolve_alias(selected_ip, "ip")
                logger.info(f"Selected library: {ip_name} ({selected_ip})")

                # Send b"tree" to the library and collect response
                try:
                    logger.info(f"Requesting tree from {ip_name}...")
                    tree_data = await discover.send_command(selected_ip, b"tree")  # async, returns bytes/JSON string
                    # Assume tree_data is JSON bytes
                    try:
                        tree_json = json.loads(tree_data.decode("utf-8"))
                    except json.decoder.JSONDecodeError:
                        logger.error(f"Failed to decode tree from {ip_name}...")
                        return None

                except Exception as e:
                    logger.error(f"Failed to get library tree: {e}")
                    return None

                lib_file_path = await asyncio.to_thread(browse_library, tree_json)

                if lib_file_path and lib_file_path != "":
                    file_selected = True
                    ip = selected_ip


            def get_free_port():
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", 0))  # Bind to loopback for security
                    return s.getsockname()[1]  # returns the assigned port

            port = get_free_port()

            data = {"port": port, "file": lib_file_path}
            json_bytes = json.dumps(data).encode("utf-8")

            header = b"send"  # your header as bytes
            message = header + json_bytes

            ok = None
            try:
                ok = await discover.send_command(ip, message)
            except OSError as e:
                if e.winerror == 10054:
                    logger.error(f"Failed to request file from {reverse_resolve_alias(ip, "ip")}...")
                    return None
            if ok != b"okay":
                logger.error(f"Request for file {lib_file_path} failed")

            server_args = None

            try:
                server_args = argparse.Namespace(
                    command='open',
                    logfile=args.logfile,
                    quiet=args.quiet,
                    verbose=args.verbose,
                    output=args.output,
                    detached=False,
                    limit=None,
                    timeout=None,
                    extract=False,
                    progress=True,
                    port=port,
                    ip=None,
                    func=None,
                    max_sends=1,
                )
            except Exception as e:
                logger.error(f"Failed to create server args: {e}")

            return server_args

        else:
            logger.warning("No libraries found")

        return None

    server_args = asyncio.run(run(args))
    if server_args:
        try:
            logger.info(f"Opening server to receive file")
            print('')
            file_server.cmd_open(server_args, logger)
        except KeyboardInterrupt:
            return
    else:
        logger.warning("File request not sent")


def cmd_open(args, logger):
    """Start the discovery responder (server)."""
    if start_detached(args, logger, LIBRARY_PID, "library"):
        return
    try:
        logger.info("Opening library...")
        asyncio.run(discover.library_server(logger))
    except KeyboardInterrupt:
        return
    except OSError as e:
        if e.winerror == 10048:
            logger.error(f"No free port for library: your library may already be opened")
        else:
            logger.error(f"Failed to open library: {e}")
    except Exception as e:
        logger.error(f"Failed to open library: {e}")


def cmd_manage(args, logger):
    """Interactive library browser/editor."""
    try:
        lm = LibraryMap(LIBRARY_FILE)
        browse_map(lm)
    except Exception as e:
        logger.error(f"Library editor failed: {e}")
