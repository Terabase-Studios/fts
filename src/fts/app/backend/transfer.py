import asyncio
import hashlib
import json
import socket
import sys
import threading
import time
from functools import partial
from pathlib import Path
from ssl import SSLContext

import fts.core.secure as secure
import fts.py as fts
from fts.app.backend.contacts import replace_with_contact, ONLINE_USERS, replace_with_ip
from fts.app.config import SAVE_DIR, logger
from fts.manager import Manager

TRANSFER_PORT = 9064
REQUEST_MSG = b"request"
AWAIT_MSG = b"await"
ACCEPT_MSG = b"accept"
REJECT_MSG = b"reject"
transfer_handler = None

class NullLogger():
    def debug(self, *a, **kw): pass
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def critical(self, *a, **kw): pass
    def exception(self, *a, **kw): pass
    def log(self, *a, **kw): pass
    def setLevel(self, *a, **kw): pass
    def addHandler(self, *a, **kw): pass

Logger = NullLogger()


async def get_free_port() -> int:
   with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    	s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    	s.bind(('', 0))
    	port = s.getsockname()[1]
    	return port


class RequestResponder():
    def __init__(self, port: int = TRANSFER_PORT):
        self.port = port
        self.queue = asyncio.Queue()
        thread = threading.Thread(target=self._thread_target, daemon=True)
        thread.start()

    def _thread_target(self):
        asyncio.run(self._run_responder(self.port))

    async def _run_responder(self, port: int):
        logger.info(f"[RequestResponder] Reponder started")
        while True:
            try:
                ssl_context: SSLContext = secure.get_server_context()
                server = await asyncio.start_server(self._respond, "0.0.0.0", port, ssl=ssl_context)
                async with server:
                    await server.serve_forever()
            except Exception as e:
                await asyncio.sleep(1)

    async def _respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            logger.info(f"[RequestResponder] Reponder responding to {writer.get_extra_info('peername')}")
            msg = await reader.read(len(REQUEST_MSG))
            if msg == REQUEST_MSG:
                addr = writer.get_extra_info('peername')[0]
                port = await get_free_port()
                writer.write(bytes(str(port), 'utf-8') + b'\n')
                logger.debug(f"[RequestResponder][QueueEvent] Adding {addr}({port}) to queue")
                await self.queue.put((addr, port))
                logger.debug(f"[RequestResponder][QueueEvent] Added to queue: {list(self.queue._queue)}")
                return
        except Exception as e:
            logger.error(f"[RequestResponder] Responser failed: {e}")


class TransferHandler:
    def __init__(self, transfer_ui, requests_ui, receive=True):
        self._running = True
        self.transfer_ui = transfer_ui
        self.requests_ui = requests_ui
        self.sending_entries = {}
        self.receiving_entries = {}
        self._lock = asyncio.Lock()
        self.send_queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        if receive:
            # Start responder in its own thread
            self.responder = RequestResponder()
            loop.create_task(self.check_queue())

        loop.create_task(self.check_send_queue())

    def send_safe(self, ip, abs_path, library=False):
        self.send_queue.put_nowait((ip, abs_path, library))
        logger.debug(f"[TransferHandler][QueueEvent][Send] send_safe added: {abs_path}->{ip} to send_queue")


    async def check_send_queue(self):
        while True:
            info = await self.send_queue.get()  # await asyncio.Queue
            if info:
                logger.debug(f"[TransferHandler][QueueEvent][Send] Found item in send_queue: {info}")
                await self.send(info[0], info[1], library=info[2])
            await asyncio.sleep(1)
            loop = asyncio.get_event_loop()
            task = loop.create_task(self.check_send_queue())


    async def check_queue(self):
        while True:
            sender = await self.responder.queue.get()  # await asyncio.Queue
            if sender:
                logger.debug(f"[TransferHandler][QueueEvent] Found item in queue: {sender}")
                await self.respond_to_requests(sender)
            await asyncio.sleep(1)
            loop = asyncio.get_event_loop()
            task = loop.create_task(self.check_queue())

    async def respond_to_requests(self, sender: tuple[str, int]):
        logger.info("[TransferHandler][Receive] Receive started")
        host, port = sender
        ssl_context = secure.get_server_context()

        # Use an event to wait for one connection
        connection_handled = asyncio.Event()

        async def handle_recieve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            logger.debug("[TransferHandler][Receive] Receive server started")
            try:
                data = await reader.readline()
                if not data:
                    return

                entry_data = json.loads(data.decode())
                entry = Entry(None, sender)
                entry.from_dict(entry_data)

                id_string = f"{entry.size}:{str(entry.port)}".encode()
                entry_id = hashlib.sha256(id_string).hexdigest()
                transfer = Transfer(entry, entry_id)
                async with self._lock:
                    self.receiving_entries[entry_id] = (entry, transfer)

                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self.requests_ui.add_request, entry, transfer)

                writer.write(AWAIT_MSG)
                await writer.drain()

                response = None
                while response is None:
                    try:
                        response = await asyncio.wait_for(reader.readline(), timeout=0.1)
                        if response:
                            response = response.strip()
                        else:
                            # Connection closed
                            raise Exception("Peer disconnected")
                    except asyncio.TimeoutError:
                        # No data yet — check for cancellation or perform other tasks
                        if transfer.cancelled.is_set():
                            writer.write(REJECT_MSG + b"\n")
                            await writer.drain()
                            raise Exception("Cancelled Transfer")
                        if transfer.accepted.is_set():
                            writer.write(ACCEPT_MSG + b"\n")
                            await writer.drain()
                            break
                        if sender[0] not in replace_with_ip(ONLINE_USERS.get_online()):
                            transfer.request_ui.remove()
                            raise Exception("Peer went offline")

                if response == REJECT_MSG:
                    transfer.request_ui.remove()
                    raise Exception("Transfer cancelled by sender")

                writer.write(ACCEPT_MSG + b'\n')
                await writer.drain()
                # noinspection PyTypeChecker
                new_port: int = await get_free_port()
                writer.write(bytes(str(new_port), "utf-8") + b'\n')
                await writer.drain()
                transfer.port = int(new_port)
                manager = Manager(no_dict=True)
                transfer.manager = manager

                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self.transfer_ui.add_active, entry, transfer, manager)

                await self.run_in_thread(fts.open, SAVE_DIR, "0.0.0.0", new_port, protected=False, max_concurrent_transfers=1, max_transfers=1, progress=True, manager=manager)
                manager.progress = manager.max_progress
                if manager.cancelled:
                    writer.write(REJECT_MSG + b"\n")
                if not transfer.cancelled.is_set():
                    await asyncio.sleep(2)

                transfer.transfer_ui.remove()

            except Exception as e:
                self.transfer_ui.notify(f"{e}", title="Error receiving transfer", severity="error")
                logger.error(f"[TransferHandler][Receive] Receive failed: {e}")

            finally:
                writer.close()
                await writer.wait_closed()
                connection_handled.set()  # Signal that we're done
                logger.info("[TransferHandler][Receive] Received function closed")

        try:
            server = await asyncio.start_server(
                handle_recieve,
                "0.0.0.0",
                port,
                ssl=ssl_context
            )

            async def handle_once():
                async with server:
                    await connection_handled.wait()
                    server.close()
                    await server.wait_closed()

            asyncio.create_task(handle_once())
        except Exception as e:
            self.transfer_ui.notify(f"{e}", title="Error receiving transfer", severity="error")
            logger.error(f"[TransferHandler][Receive] Failed to start server: {e}")

    async def send(self, target: str, filepath: str, library=False):
        if library:
            logger.debug(f"[TransferHandler][Send] Received a library request from {target} for {filepath}")
            self.transfer_ui.notify(f"Received a library request from {target} for {filepath}", title="Your library")

        logger.info("[TransferHandler][Send] Sending started")
        writer = None
        reader = None
        try:
            # Phase 1: request transfer port
            connected = False
            tries = 0
            while not connected and tries < 3:
                try:
                    reader, writer = await secure.connect_with_tofu_async(target, TRANSFER_PORT, Logger)
                except Exception as e:
                    time.sleep(1)
                    tries += 1
                    if tries >= 3:
                        raise e
                else:
                    connected = True
            writer.write(REQUEST_MSG + b"\n")
            await writer.drain()
            port_line = await reader.readline()
            writer.close()
            await writer.wait_closed()

            receiver = (target, int(port_line.decode().strip()))

            # Phase 2: send entry metadata
            entry = Entry(filepath, receiver)
            id_string = f"{entry.size}:{str(entry.port)}".encode()
            entry_id = hashlib.sha256(id_string).hexdigest()
            transfer = Transfer(entry, entry_id)
            async with self._lock:
                self.sending_entries[entry_id] = (entry, transfer)

            connected = False
            tries = 0
            while not connected and tries < 3:
                try:
                    reader, writer = await secure.connect_with_tofu_async(receiver[0], receiver[1], Logger)
                except Exception as e:
                    time.sleep(1)
                    tries += 1
                    if tries >= 3:
                        raise e
                else:
                    connected = True
            data = json.dumps(entry.to_dict()).encode() + b"\n"
            writer.write(data)
            await writer.drain()

            msg = await reader.read(len(AWAIT_MSG))
            if not msg == AWAIT_MSG:
                raise Exception(f"Expected AWAIT_MSG got {msg}")

            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self.transfer_ui.add_inactive, entry, transfer)

            response = None
            while response is None:
                try:
                    response = await asyncio.wait_for(reader.readline(), timeout=0.1)
                    if response:
                        response = response.strip()
                    else:
                        # Connection closed
                        raise Exception("Peer disconnected")
                except asyncio.TimeoutError:
                    # No data yet — check for cancellation or perform other tasks
                    if transfer.cancelled.is_set():
                        writer.write(REJECT_MSG + b"\n")
                        await writer.drain()
                        transfer.transfer_ui.remove()
                        raise Exception("Transfer cancelled")

                    if target not in replace_with_ip(ONLINE_USERS.get_online()):
                        transfer.transfer_ui.remove()
                        raise Exception("Peer went offline")


            if response == ACCEPT_MSG:
                self.transfer_ui.notify(f"{replace_with_contact(target)} accepted {entry.name}", title="Transfer Accepted", severity="information")
            elif response == REJECT_MSG:
                writer.close()
                await writer.wait_closed()
                transfer.transfer_ui.remove()
                raise Exception("Transfer denied by receiver")
            else:
                writer.close()
                await writer.wait_closed()
                transfer.transfer_ui.remove()
                raise Exception(f"Expected ACCEPT_MSG got {response}")

            transfer.transfer_ui.remove()

            await reader.readline()
            new_port = await reader.readline()
            new_port = new_port.decode("utf-8").strip()
            transfer.port = int(new_port)
            manager = Manager(no_dict=True)
            transfer.manager = manager

            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self.transfer_ui.add_active, entry, transfer, manager)

            await self.run_in_thread(fts.send, filepath, target, new_port, manager=manager, progress=True)
            manager.progress = manager.max_progress
            if manager.cancelled:
                writer.write(REJECT_MSG + b"\n")
            if not transfer.cancelled.is_set():
                await asyncio.sleep(2)

            transfer.transfer_ui.remove()

        except Exception as e:
            self.transfer_ui.notify(f"{e}", title="Error sending transfer", severity="error")
            logger.error(f"[TransferHandler][Send] Recieve failed: {e}")

        finally:
            if writer:
                writer.close()
                await writer.wait_closed()

            logger.info("[TransferHandler][Send] Sending function closed")

    async def run_in_thread(self, func, *args, **kwargs):
        """
        Async wrapper that runs `func` in a separate thread safely.
        """

        def safe_run(func, *args, **kwargs):
            """
            Runs a function safely, even if it uses asyncio.run() internally.
            Should be called from a separate thread.
            """
            try:
                return func(*args, **kwargs)
            except RuntimeError as e:
                if "asyncio.run() cannot be called from a running event loop" in str(e):
                    # Function tried to run its own event loop — run it in a new thread
                    # Already in a thread here, so just run normally
                    return func(*args, **kwargs)
                else:
                    raise
        return await asyncio.to_thread(partial(safe_run, func, *args, **kwargs))

    def cancel_all(self):
        logger.debug("[TransferHandler][Cancel] Cancelling all transfers")
        for receiving in self.receiving_entries.values():
            transfer = receiving[1]
            transfer.cancelled.set()
            if transfer.manager:
                transfer.manager.cancelled = True

        for sending in self.sending_entries.values():
            transfer = sending[1]
            transfer.cancelled.set()
            if transfer.manager:
                transfer.manager.cancelled = True
        logger.info(f"[TransferHandler][Cancel] Finished cleanup")


class Transfer():
    def __init__(self, entry, entry_id):
        self.accepted = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.entry = entry
        self.entry_id = entry_id
        self.request_ui = None
        self.transfer_ui = None
        self.progress = 0
        self.max_progress = 0
        self.manager = None


class Entry():
    def __init__(self, filepath: str | None, target_info: tuple[str, int] | None):
        self.filepath = None
        self.name = None
        self.size = None
        self.target = None
        self.port = None
        if filepath:
            self.filepath = Path(filepath)
            self.name = self.filepath.name
            self.size = self.filepath.stat().st_size
        if target_info:
            self.target = target_info[0]
            self.port = target_info[1]

    def to_dict(self):
        return {
            "filepath": str(self.filepath),
            "name": self.name,
            "size": self.size,
            "target": self.target,
            "port": self.port,
        }

    def from_dict(self, data: dict):
        self.name = data["name"]
        try:
            self.size = int(data["size"])
            self.port = int(data["port"])
        except:
            pass

