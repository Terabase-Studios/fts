import asyncio
import itertools
import os
import random
import re
import shutil
import string
import struct
import tempfile
import time
import zlib
from pathlib import Path

from tqdm.asyncio import tqdm_asyncio as tqdm

import fts.flags as transferflags
from fts.config import (
    DEFAULT_FILE_PORT,
    MAGIC,
    VERSION,
    BUFFER_SIZE,
    BATCH_SIZE,
    PROGRESS_INTERVAL,
    RECEIVING_PID,
    MID_DOWNLOAD_EXT,
)
from fts.core import secure as secure
from fts.core.detatched import start_detached
from fts.core.dosp import should_receive
from fts.manager import Manager
from fts.utilities import format_bytes, parse_byte_string

# Incrementing IDs for each client connection
_client_ids = itertools.count(1)

def cmd_open(args, logger, manager=None):
    """Start TLS receiver server safely with dynamic port handling and shutdown support."""
    if not args.output:
        logger.error("No path given")
        return

    if start_detached(args, logger, RECEIVING_PID, "receiving"):
        return

    logger.info(f"Preparing to receive files to '{args.output}'")
    logger.debug(f"Options: {vars(args)}")

    host = args.ip or "0.0.0.0"
    output_dir = os.path.abspath(args.output or ".")
    os.makedirs(output_dir, exist_ok=True)
    port = args.port or DEFAULT_FILE_PORT

    limit = 0
    if args.limit:
        try:
            limit = parse_byte_string(args.limit)
        except Exception as e:
            logger.error(f"Error parsing limit: {e}\n")
            return

    max_sends = None
    if hasattr(args, "max_sends") and args.max_sends is not None:
        max_sends = args.max_sends

    # Try dynamic port handling BEFORE running asyncio
    for attempt in range(45):
        try:
            server_coro = start_server(host, port, output_dir, logger, args.progress, limit, max_sends, args.unprotected, args.max_transfers, manager=manager)
            asyncio.run(server_coro)
            return
        except OSError as e:
            if port != 0:
                logger.warning(f"Error connecting to port: {e}")
                logger.warning(f"Port {port} unavailable, retrying with free port...")
                port +=1
            else:
                logger.error(f"Failed to start server: {e}")
                return
        except asyncio.CancelledError:
            logger.info("Server shutdown requested by user")
            return
        except KeyboardInterrupt:
            logger.info("Server shutdown requested by user")
            return
        except Exception as e:
            logger.critical(f"Server error: {e}")
            return


async def start_server(host: str, port: int, output_dir: str, logger,
                       progress_bar=False, rate_limit: int = 0, max_sends=None, unprotected=False, max_concurrent_transfers=0, manager: Manager = None):
    from ssl import SSLContext
    ssl_context: SSLContext = secure.get_server_context()
    os.makedirs(output_dir, exist_ok=True)

    send_counter = 0
    current_transfers = 0
    shutdown_event = asyncio.Event()  # will signal server shutdown

    if manager:
        if manager.in_use:
            manager = None
            logger.warning("Cannot use the same manager twice!\n Detaching manager")
        else:
            manager.in_use = True
            manager.type = "receive"

    async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal send_counter
        nonlocal current_transfers
        nonlocal manager
        nonlocal max_sends
        client_id = next(_client_ids)
        addr = writer.get_extra_info('peername')
        if max_concurrent_transfers and current_transfers >= max_concurrent_transfers:
            writer.write(b"HOLD")
            await writer.drain()
            if manager:
                if manager.cancelled:
                    logger.error("Manager cancelled transfer")
                    raise Exception("Cancelled by manager")

                if not manager.no_dict:
                    p = manager.state
                    p[client_id] = "holding"
                    manager.state = p
                else:
                    manager.state = "holding"
            while current_transfers >= max_concurrent_transfers:
                await asyncio.sleep(1)


        try:
            if manager:
                if manager.cancelled:
                    logger.error("Manager cancelled transfer")
                    raise Exception("Cancelled by manager")

                if not manager.no_dict:
                    p = manager.state
                    p[client_id] = "awaiting"
                    manager.state = p
                else:
                    manager.state = "awaiting"
            current_transfers += 1
            file_sent = await handle_client(reader, writer, output_dir, client_id,
                                            logger, progress_bar, rate_limit, unprotected, manager=manager)

        except Exception as e:
            logger.error(f"{client_id}: Unhandled client exception: {e}", exc_info=True)
            if manager:
                if not manager.no_dict:
                    p = manager.state
                    p[client_id] = "failed"
                    manager.state = p
                else:
                    manager.state = "failed"
        else:
            if manager:
                if not manager.no_dict:
                    p = manager.state
                    p[client_id] = "finished"
                    manager.state = p
                else:
                    manager.state = "finished"

        finally:
            current_transfers -= 1

            if max_sends is not None:
                send_counter += 1
                logger.info(f"{client_id}: Transfer requests: {send_counter}/{max_sends}")
                if send_counter >= max_sends:
                    logger.info("Maximum transfer requests reached, closing server")
                    shutdown_event.set()  # trigger server shutdown


            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                pass
            logger.info(f"{client_id}: Connection from {addr} closed\n")

    server = await asyncio.start_server(handle_connection, host, port, ssl=ssl_context)
    logger.info(f"Server listening on {host}:{port}\n")

    # Start serving connections in the background
    server_task = asyncio.create_task(server.serve_forever())

    # Wait for shutdown signal
    await shutdown_event.wait()
    server.close()
    await server.wait_closed()
    server_task.cancel()
    logger.info("Server shutdown after max transfer requests reached")


def uniquify_filename(filename, directory="."):
    """
    Ensures filename is unique in the given directory.
    Adds or increments (number) suffix only if a conflict exists.
    Handles cases like:
        example.txt       → example.txt
        example.txt*2     → example(1).txt, example(2).txt
        example(5).txt    → example(6).txt
    """
    base, ext = os.path.splitext(filename)
    path = Path(directory)

    # If no file exists, return as-is
    if not (path / filename).exists():
        return filename

    # Detect existing numeric suffix (e.g., (5))
    match = re.search(r"\((\d+)\)$", base)
    if match:
        base_name = base[:match.start()]
    else:
        base_name = base

    # Find highest existing number for the pattern
    existing_numbers = [0]
    for existing in path.glob(f"{base_name}*{ext}"):
        m = re.search(rf"^{re.escape(base_name)}\((\d+)\){re.escape(ext)}$", existing.name)
        if m:
            existing_numbers.append(int(m.group(1)))
        elif existing.name == filename:
            existing_numbers.append(0)

    new_number = max(existing_numbers) + 1
    return f"{base_name}({new_number}){ext}"


async def safe_rename(temp_path: Path, out_path: Path):
    """
    Renames temp_path → out_path, automatically increments numeric suffixes like (1), (2), etc.
    Example:
        example.txt     → example.txt
        example.txt     (exists) → example(1).txt
        example(5).txt  (exists) → example(6).txt
    """
    directory = out_path.parent
    filename = out_path.name

    unique_name = uniquify_filename(filename, str(directory))
    target = directory / unique_name
    temp_path.rename(target)
    return target


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, output_dir: str, client_id, logger, progress_bar=False, rate_limit: int = 0, unprotected=False, manager: Manager = None):
    addr = writer.get_extra_info("peername")
    logger.info(f"{client_id}: Secure connection from {addr}")

    try:
        valid, error = True, ""
        # --- Parse header ---
        header_data = await reader.readexactly(19)
        magic, version, flags, fname_len, filesize = struct.unpack(">4sfBHQ", header_data)
        checksum_bytes = await reader.readexactly(4)
        checksum = struct.unpack(">I", checksum_bytes)[0]
        filename_bytes = await reader.readexactly(fname_len)
        filename = filename_bytes.decode("utf-8")
        # make sure filename is unique
        filename = uniquify_filename(filename, output_dir)

        # --- Validate ---
        if magic != MAGIC:
            valid, error = False, "Invalid magic number in header"
        if int(VERSION * 1000) != int(version * 1000):
            valid, error = False, "Version mismatch between sender and receiver"
        if fname_len > 1024:
            valid, error = False, "Recieving filename to longer than 1024 bytes"

        calc_checksum = zlib.crc32(filename_bytes + struct.pack(">Q", filesize)) & 0xFFFFFFFF
        if calc_checksum != checksum:
            valid, error = False, "Header checksum mismatch! The sent header may have been corrupted."

        # --- Prepare output ---
        out_path = os.path.join(output_dir, os.path.basename(filename))
        logger.info(f"{client_id}: Receiving '{filename}' ({format_bytes(filesize)}) into {output_dir}")

        if valid:
            valid, error = should_receive(addr, filesize, flags)
        if valid or unprotected:
            writer.write(b"SEND")
            if not valid:
                logger.debug(f"{client_id}: Request failed verification but server is set to unprotected: \n{error}\n")
            else:
                logger.debug(f"{client_id}: Permission to send file sent to server")
        else:
            writer.write(b"DENY")
            logger.error(f"{client_id}: Sender failed request validation: \n{error}\n")
            raise Exception("Sender request denied by server")
        await writer.drain()

        if manager:
            if manager.cancelled:
                logger.error("Manager cancelled transfer")
                raise Exception("Cancelled by manager")

            if not manager.no_dict:
                p = manager.state
                p[client_id] = "transferring"
                manager.state = p
                p = manager.max_progress
                p[client_id] = filesize
                manager.max_progress = p

            else:
                manager.state = "transferring"
                manager.max_progress = filesize


        os.makedirs(output_dir, exist_ok=True)

        # generate 16 random characters
        rand = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        temp_path = Path(out_path).with_name(f"{Path(out_path).stem}{rand}){Path(out_path).suffix}").with_suffix(MID_DOWNLOAD_EXT)

        # --- Receive file ---
        received = await receive_linear(reader, filesize, temp_path, client_id, logger, progress_bar=progress_bar, rate_limit=rate_limit, manager=manager)


        if received < filesize:
            logger.error(f"{client_id}: Incomplete file received: {format_bytes(received)}/{format_bytes(filesize)}")
            os.remove(temp_path)
            if manager:
                if manager.cancelled:
                    logger.error("Manager cancelled transfer")
                    raise Exception("Cancelled by manager")

                if not manager.no_dict:
                    p = manager.state
                    p[client_id] = "failed"
                    manager.state = p
                else:
                    manager.state = "failed"
            return

        await writer.drain()
        writer.write(b"OKAY")
        await writer.drain()
        logger.info(f"{client_id}: File received successfully: {filename}")

        # --- Decompress if needed ---
        if flags & transferflags.FLAG_COMPRESSED:
            if manager:
                if manager.cancelled:
                    logger.error("Manager cancelled transfer")
                    raise Exception("Cancelled by manager")

                if not manager.no_dict:
                    p = manager.state
                    p[client_id] = "decompressing"
                    manager.state = p
                else:
                    manager.state = "decompressing"
            temp_path = await asyncio.to_thread(decompress_file, str(temp_path), client_id, logger)

        final_path = await safe_rename(Path(temp_path), Path(out_path))
        logger.info(f"Saved as: {final_path}")

    except Exception as e:
        logger.exception(f"{client_id}: Error receiving file: {e}")
        if manager:
            if manager.cancelled:
                logger.error("Manager cancelled transfer")
                raise Exception("Cancelled by manager")

            if not manager.no_dict:
                p = manager.state
                p[client_id] = "failed"
                manager.state = p
            else:
                manager.state = "failed"
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def receive_linear(reader, filesize, out_path, client_id, logger, progress_bar=False, rate_limit: int = 0, manager: Manager = None):
    """
    High-performance async file receiver using batch reads and memoryview,
    with thread-based file writes to avoid blocking the event loop and optional rate limiting.
    """

    received = 0
    last_progress_update = time.monotonic()
    next_recv_time = time.monotonic()
    start_time = 0
    end_time = 0
    progress = tqdm(
        total=filesize,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        disable=not progress_bar,
        leave=False,
        desc = f"{client_id}",
    )

    # Helper function to write a chunk in a thread
    def write_chunk(f1, mv1):
        f1.write(mv1)

    try:
        start_time = time.monotonic()
        with open(out_path, "wb") as f:  # regular file
            while received < filesize:
                chunk_size = min(BUFFER_SIZE * BATCH_SIZE, filesize - received)
                if chunk_size <= 0:
                    break

                try:
                    chunk = await asyncio.wait_for(reader.read(chunk_size), timeout=30)
                except (ConnectionError, OSError, asyncio.TimeoutError):
                    logger.warning(f"{client_id}: Client disconnected or read timeout")
                    break

                if not chunk:
                    break

                mv = memoryview(chunk)
                await asyncio.to_thread(write_chunk, f, mv)

                received += len(chunk)

                # Bandwidth limiting
                if rate_limit > 0:
                    now = time.monotonic()
                    target_time = len(chunk) / rate_limit
                    if now < next_recv_time:
                        await asyncio.sleep(next_recv_time - now)
                    next_recv_time = max(now, next_recv_time) + target_time

                # Periodic progress update
                now = time.monotonic()
                if progress_bar and now - last_progress_update >= PROGRESS_INTERVAL:
                    progress.n = received
                    progress.refresh()
                    if manager:
                        if manager.cancelled:
                            logger.error("Manager cancelled transfer")
                            raise Exception("Manager cancelled transfer")

                        if not manager.no_dict:
                            p = manager.progress
                            p[client_id] = received
                            manager.state = p
                        else:
                            manager.progress = received
                    last_progress_update = now
            end_time = time.monotonic()

    finally:
        duration = end_time - start_time
        # Final progress update
        if progress_bar:
            progress.n = received
            progress.refresh()
            if manager:
                manager.progress = received
        progress.close()
        logger.debug(f"{client_id}: Transferred {format_bytes(received)} in {duration:.2f} seconds: ({format_bytes(received / duration)}/s)")
    return received


# --- Sync helper functions for CPU-bound work ---
def decompress_file(file_path: str, client_id, logger):
    temp_dir = tempfile.mkdtemp()
    decompressed_path = os.path.join(temp_dir, os.path.basename(file_path).removesuffix(".zlib"))
    try:
        logger.info(f"{client_id}: Decompressing {file_path}...")
        with open(file_path, "rb") as f_in, open(decompressed_path, "wb") as f_out:
            decompressor = zlib.decompressobj()
            while chunk := f_in.read(64 * 1024):
                f_out.write(decompressor.decompress(chunk))
            f_out.write(decompressor.flush())
        os.remove(file_path)
        final_path = os.path.join(os.path.dirname(file_path), os.path.basename(decompressed_path))
        shutil.move(decompressed_path, final_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"{client_id}: Decompression complete")
        return final_path
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"{client_id}: Failed to decompress: {e}")
        raise
