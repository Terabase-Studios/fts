import asyncio
import json
import os

import fts.commands.sender as sender
from fts.config import DISCOVERY_PORT
from fts.config import LIBRARY_FILE
from fts.core.aliases import reverse_resolve_alias
from fts.library.map import LibraryMap
from fts.library.tree import build_library_tree

DISCOVERY_MESSAGE = b"ping"
TREE_MESSAGE = b"tree"
RESPONSE_MESSAGE = b"okay"
SEND_MESSAGE = b"send"
OK_MESSAGE = b"okay"


# noinspection PyTypeChecker
async def library_server(logger):
    """Server: listens for discovery pings and replies 'okay'."""
    loop = asyncio.get_event_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: DiscoveryResponder(logger),
        local_addr=("0.0.0.0", DISCOVERY_PORT),
        allow_broadcast=True
    )
    logger.info("Library server listening on port %d\n", DISCOVERY_PORT)
    try:
        await asyncio.Future()  # run forever
    finally:
        transport.close()
        logger.info("Library closing")

class DiscoveryResponder:
    def __init__(self, logger):
        self.logger = logger
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.logger.debug("Library connection")

    def datagram_received(self, data, addr):
        addr_name = reverse_resolve_alias(addr[0], "ip")
        self.logger.debug(f"Received {data!r} from {addr_name}")
        if data == DISCOVERY_MESSAGE:
            self.transport.sendto(RESPONSE_MESSAGE, addr)
            print('')
            self.logger.info(f"Sent discovery response to {addr_name}")
        elif data == TREE_MESSAGE:
            library_map = LibraryMap(LIBRARY_FILE)
            tree = build_library_tree(library_map.map)
            json_string = json.dumps(tree)
            data_to_send = json_string.encode("utf-8")
            self.transport.sendto(data_to_send, addr)
            self.logger.info(f"Sent library tree to {addr_name}")
        elif data.startswith(SEND_MESSAGE):
            json_payload = data[len(SEND_MESSAGE):]  # strip header
            obj = json.loads(json_payload.decode("utf-8"))
            self.logger.info(f"Received SEND message from {addr_name}: port={obj['port']}, file={obj['file']}")
            self.transport.sendto(OK_MESSAGE, addr)
            self.logger.debug(f"Sent OK response to {addr_name}\n")
            print("")


            try:
                ip, udp_port = addr
                file_path = LibraryMap(LIBRARY_FILE).get_real_path(obj['file'])
                asyncio.create_task(
                    sender.send_file(
                        file_path=file_path,
                        host=ip,
                        port=obj["port"],
                        logger=self.logger,
                        progress_bar=True,
                        name=os.path.basename(obj['file'])
                    )
                )
            except Exception as e:
                self.logger.error(f"Failed to send {obj['file']} to {addr_name}: {e}")

    def connection_lost(self, exc):
        self.logger.debug("Library connection lost")


# noinspection PyTypeChecker
async def discover_libraries(timeout=2.0):
    """Client: broadcasts 'ping' and collects all 'okay' responses."""
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: DiscoveryCollector(),
        local_addr=("0.0.0.0", 0),
        allow_broadcast=True
    )

    # Send broadcast
    transport.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", DISCOVERY_PORT))

    # Wait for responses
    await asyncio.sleep(timeout)
    ips = protocol.responses
    transport.close()
    return ips

class DiscoveryCollector:
    def __init__(self):
        self.responses = set()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if data == RESPONSE_MESSAGE:
            self.responses.add(addr[0])

    def connection_lost(self, exc):
        # Required on Windows to avoid AttributeError when transport closes
        pass


# noinspection PyTypeChecker,GrazieInspection
async def send_command(ip: str, data: bytes, timeout: float = 2.0) -> bytes:
    """
    Send a command to a server and wait for response (UDP).

    :param ip: server IP
    :param data: bytes to send
    :param timeout: seconds to wait for response
    :return: response bytes
    """
    loop = asyncio.get_event_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: _CommandClientProtocol(data),
        remote_addr=(ip, DISCOVERY_PORT),
    )

    try:
        # Wait for response with timeout
        response = await asyncio.wait_for(protocol.response_future, timeout)
        return response
    finally:
        transport.close()


class _CommandClientProtocol:
    def __init__(self, message: bytes):
        self.message = message
        self.transport = None
        self.response_future = asyncio.get_event_loop().create_future()

    def connection_made(self, transport):
        self.transport = transport
        self.transport.sendto(self.message)

    def datagram_received(self, data, addr):
        if not self.response_future.done():
            self.response_future.set_result(data)

    def error_received(self, exc):
        if not self.response_future.done():
            self.response_future.set_exception(exc)

    def connection_lost(self, exc):
        if not self.response_future.done():
            if exc:
                self.response_future.set_exception(exc)
            else:
                self.response_future.set_result(b"")