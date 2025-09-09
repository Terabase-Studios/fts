import asyncio
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
import time
import itertools

import psutil
from tqdm.asyncio import tqdm_asyncio as tqdm

import fts.flags as transferflags
from fts.config import (
    DEFAULT_FILE_PORT,
    MAGIC,
    VERSION,
    BUFFER_SIZE,
    BATCH_SIZE,
    PROGRESS_INTERVAL,
    PID_FILE,
)
from fts.core import secure as secure
from fts.utilities import format_bytes, parse_byte_string

# Incrementing IDs for each client connection
_client_ids = itertools.count(1)

def start_detached(args, logger) -> bool:
    """
    Start in detached mode (completely detached: no console, no I/O).
    Returns True if parent should exit, False otherwise.
    """
    if not getattr(args, "detached", False):
        return False

    # Check for existing PID
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            if psutil.pid_exists(old_pid):
                p = psutil.Process(old_pid)
                logger.info(f"Server already running (PID {old_pid})")
                logger.info("Run 'fts close' to end current server")
                logger.debug(f"cmd: {' '.join(p.cmdline())}")
                return True
            else:
                logger.warning("Stale PID file found, removing")
                os.remove(PID_FILE)
        except Exception as e:
            logger.warning(f"Failed to read PID file: {e}")
            os.remove(PID_FILE)

    # Copy args but remove -d/--detached
    arguments = sys.argv[1:].copy()
    for flag in ("-d", "--detached"):
        if flag in arguments:
            arguments.remove(flag)

    # Prefer installed CLI script, fallback to -m
    fts_executable = shutil.which("fts")
    if fts_executable:
        cmd = [fts_executable] + arguments
    else:
        cmd = [sys.executable, "-m", "fts"] + arguments

    # Prepare kwargs for Popen
    startupinfo = subprocess.STARTUPINFO() if os.name == "nt" else False
    if startupinfo:
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    kwargs = dict(
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )

    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        kwargs["startupinfo"] = startupinfo
    else:
        kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **kwargs, shell=False)
        # Write PID to file
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
        logger.info(f"Server started in detached mode (PID {proc.pid})")
    except Exception as e:
        logger.error(f"Error launching server: {e}")
        return True

    # Parent should exit
    return True


def cmd_open(args, logger):
    """Start TLS receiver server safely with dynamic port handling and shutdown support."""
    if start_detached(args, logger):
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

    # Try dynamic port handling BEFORE running asyncio
    for attempt in range(5):
        try:
            server_coro = start_server(host, port, output_dir, logger, args.extract, args.progress, rate_limit=limit)
            asyncio.run(server_coro)
            return
        except OSError as e:
            if port != 0:
                logger.warning(f"Port {port} unavailable, retrying with free port...")
                port = 0
            else:
                logger.error(f"Failed to start server: {e}")
                sys.exit(1)
        except KeyboardInterrupt:
            logger.info("Server shutdown requested by user")
            return
        except Exception as e:
            logger.critical(f"Server error: {e}")
            sys.exit(1)



async def start_server(host: str, port: int, output_dir: str, logger, extract=False, progress_bar=False, rate_limit: int = 0):
    """
    Starts an async SSL server that listens for incoming connections, handles clients,
    and saves files to output_dir. Logs progress.
    """
    from ssl import SSLContext
    ssl_context: SSLContext = secure.get_server_context()

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client_id = next(_client_ids)
        addr = writer.get_extra_info('peername')

        try:
            await handle_client(reader, writer, output_dir, client_id, logger, extract, progress_bar, rate_limit=rate_limit)
        except Exception as e:
            logger.error(f"{client_id}: Unhandled client exception: {e}", exc_info=True)
        finally:
            try:
                writer.close()
            except Exception:
                pass

            logger.info(f"{client_id}: Connection from {addr} closed\n")


    server = await asyncio.start_server(handle_connection, host, port, ssl=ssl_context)
    logger.info(f"Server listening on {host}:{port}\n")
    async with server:
        await server.serve_forever()


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, output_dir: str, client_id, logger, extract=False, progress_bar=False, rate_limit: int = 0):
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
            logger.warning(f"{client_id}: Incomplete file received: {format_bytes(received)}/{format_bytes(filesize)}")
            os.remove(out_path)
            return

        await writer.drain()
        writer.write(b"OKAY")
        await writer.drain()
        logger.info(f"{client_id}: File received successfully: {filename}")

        # --- Decompress if needed ---
        if flags & transferflags.FLAG_COMPRESSED:
            out_path = await asyncio.to_thread(decompress_file, out_path, logger)

        # --- Extract zip if requested ---
        if extract and zipfile.is_zipfile(out_path):
            await asyncio.to_thread(extract_zip, out_path, logger)

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
        with open(out_path, "wb") as f:  # regular file
            while received < filesize:
                chunk_size = min(BUFFER_SIZE * BATCH_SIZE, filesize - received)
                if chunk_size <= 0:
                    break

                try:
                    chunk = await asyncio.wait_for(reader.read(chunk_size), timeout=30)
                except (ConnectionResetError, OSError, asyncio.TimeoutError):
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

    finally:
        # Final progress update
        if progress_bar:
            progress.n = received
            progress.refresh()
        progress.close()
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


def extract_zip(zip_path, client_id, logger):
    if not zipfile.is_zipfile(zip_path):
        logger.error(f"{client_id}: Not a valid zip file: {zip_path}")
        return

    try:
        base_path = os.path.splitext(zip_path)[0]
        extract_path = base_path + "_extracting"
        final_path = base_path

        os.makedirs(extract_path, exist_ok=True)

        logger.info(f"{client_id}: Extracting zip to {extract_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

        try:
            os.remove(zip_path)
        except Exception as e:
            logger.warning(f"{client_id}: Failed to remove original zip: {e}")

        if os.path.exists(final_path):
            logger.warning(f"{client_id}: Final path already exists, overwriting: {final_path}")
            # Optional: remove or merge existing folder
            # shutil.rmtree(final_path)

        os.rename(extract_path, final_path)
        logger.info(f"{client_id}: Extracted zip to {final_path}")

    except Exception as e:
        logger.error(f"{client_id}: Zip extraction error: {e}")
        raise


def cmd_close(args, logger):
    """
    Stops the detached FTS server if it's running.
    """

    logger.debug(f"Preparing to close server")
    logger.debug(f"Options: {vars(args)}")

    if not os.path.exists(PID_FILE):
        logger.warning("No PID file found, server may not be running.")
        return

    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except Exception as e:
        logger.error(f"Failed to read PID file: {e}")
        return

    if not psutil.pid_exists(pid):
        logger.warning(f"No process with PID {pid} found. Removing stale PID file.")
        os.remove(PID_FILE)
        return

    try:
        proc = psutil.Process(pid)
        logger.info(f"Stopping server (PID {pid})")
        logger.debug(f"cmd: {' '.join(proc.cmdline())}")
        proc.terminate()  # send SIGTERM on Unix / terminate on Windows
        try:
            proc.wait(timeout=5)  # wait up to 5 seconds
            logger.info("Server stopped successfully.")
        except psutil.TimeoutExpired:
            logger.warning("Server did not stop in time. Killing forcibly.")
            proc.kill()
        os.remove(PID_FILE)
    except Exception as e:
        logger.error(f"Failed to stop server PID {pid}: {e}")
