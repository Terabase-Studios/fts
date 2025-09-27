import asyncio
import itertools
import os
import shutil
import struct
import sys
import tempfile
import time
import zlib

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
)
from fts.core import secure as secure
from fts.core.detatched import start_detached
from fts.utilities import format_bytes, parse_byte_string

# Incrementing IDs for each client connection
_client_ids = itertools.count(1)



def cmd_open(args, logger):
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
            sys.exit(1)

    max_sends = None
    if hasattr(args, "max_sends") and args.max_sends is not None:
        max_sends = args.max_sends

    # Try dynamic port handling BEFORE running asyncio
    for attempt in range(45):
        try:
            server_coro = start_server(host, port, output_dir, logger, args.progress, limit, max_sends=max_sends)
            asyncio.run(server_coro)
            return
        except OSError as e:
            if port != 0:
                logger.warning(f"Port {port} unavailable, retrying with free port...")
                port +=1
            else:
                logger.error(f"Failed to start server: {e}")
                sys.exit(1)
        except asyncio.CancelledError:
            logger.info("Server shutdown requested by user")
            return
        except KeyboardInterrupt:
            logger.info("Server shutdown requested by user")
            return
        except Exception as e:
            logger.critical(f"Server error: {e}")
            sys.exit(1)


async def start_server(host: str, port: int, output_dir: str, logger,
                       progress_bar=False, rate_limit: int = 0, max_sends=None):
    from ssl import SSLContext
    ssl_context: SSLContext = secure.get_server_context()
    os.makedirs(output_dir, exist_ok=True)

    send_counter = 0
    shutdown_event = asyncio.Event()  # will signal server shutdown

    async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal send_counter
        client_id = next(_client_ids)
        addr = writer.get_extra_info('peername')

        try:
            file_sent = await handle_client(reader, writer, output_dir, client_id,
                                            logger, progress_bar, rate_limit)
            if max_sends is not None:
                send_counter += 1
                logger.info(f"{client_id}: Transfer requests: {send_counter}/{max_sends}")
                if send_counter >= max_sends:
                    logger.info("Maximum transfer requests reached, closing server")
                    shutdown_event.set()  # trigger server shutdown

        except Exception as e:
            logger.error(f"{client_id}: Unhandled client exception: {e}", exc_info=True)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
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
    Ensure filename is unique in the given directory.
    If filename exists, append or increment a number.
    """
    base, ext = os.path.splitext(filename)
    prefix = base.rstrip("0123456789")
    num_str = base[len(prefix):]

    # Start count from existing number or 1 if none
    start = int(num_str) if num_str.isdigit() else 1

    candidate = filename
    for i in itertools.count(start):
        if not os.path.exists(os.path.join(directory, candidate)):
            return candidate
        candidate = f"{prefix}{i}{ext}"

    return candidate


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, output_dir: str, client_id, logger, progress_bar=False, rate_limit: int = 0):
    addr = writer.get_extra_info("peername")
    logger.info(f"{client_id}: Secure connection from {addr}")

    try:
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
            raise ValueError("Invalid magic number")
        if int(VERSION * 1000) != int(version * 1000):
            raise ValueError("Version mismatch")
        if fname_len > 1024:
            raise ValueError("Filename too long")
        calc_checksum = zlib.crc32(filename_bytes + struct.pack(">Q", filesize)) & 0xFFFFFFFF
        if calc_checksum != checksum:
            raise ValueError("Header checksum mismatch")

        # --- Prepare output ---
        out_path = os.path.join(output_dir, os.path.basename(filename))
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"{client_id}: Receiving '{filename}' ({format_bytes(filesize)}) into {output_dir}")

        # --- Receive file ---
        received = await receive_linear(reader, filesize, out_path, client_id, logger, progress_bar=progress_bar, rate_limit=rate_limit)


        if received < filesize:
            logger.error(f"{client_id}: Incomplete file received: {format_bytes(received)}/{format_bytes(filesize)}")
            os.remove(out_path)
            return

        await writer.drain()
        writer.write(b"OKAY")
        await writer.drain()
        logger.info(f"{client_id}: File received successfully: {filename}")

        # --- Decompress if needed ---
        if flags & transferflags.FLAG_COMPRESSED:
            out_path = await asyncio.to_thread(decompress_file, out_path, client_id, logger)

    except Exception as e:
        logger.exception(f"{client_id}: Error receiving file: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def receive_linear(reader, filesize, out_path, client_id, logger, progress_bar=False, rate_limit: int = 0):
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
                    last_progress_update = now
            end_time = time.monotonic()

    finally:
        duration = end_time - start_time
        # Final progress update
        if progress_bar:
            progress.n = received
            progress.refresh()
        progress.close()
        logger.debug(f"Transferred {format_bytes(received)} in {duration:.2f} seconds: ({format_bytes(received / duration)}/s)")
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