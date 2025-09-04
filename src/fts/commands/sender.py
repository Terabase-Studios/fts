import os
import queue
import shutil
import socket
import struct
import sys
import tempfile
import threading
import zlib

from sympy import false
from tqdm import tqdm

import fts.flags as transferflags
from fts.config import (
    DEFAULT_PORT,
    MAGIC,
    VERSION,
    BUFFER_SIZE,
    MAX_SEND_RETRIES,
    FLUSH_SIZE,
    QUEUE_SIZE,
    UNCOMPRESSIBLE_EXTS,
)
from fts.core import secure as secure
from fts.core.zipper import zip_directory
from fts.utilities import format_bytes, parse_byte_string


# -------------------------
# Helper functions
# -------------------------
def resolve_path(path: str) -> str:
    path = os.path.expanduser(path)
    return os.path.abspath(path)

# -------------------------
# Send file over TLS
# -------------------------
def build_header(filename: str, filesize: int, flags: int = 0) -> bytes:
    filename_bytes = filename.encode('utf-8')
    fname_len = len(filename_bytes)
    if fname_len > 65535:
        raise ValueError("Filename too long")

    # Pack version as 32-bit float
    # Format: >4s f B H Q
    header_without_checksum = struct.pack(
        ">4sfBHQ",
        MAGIC,
        VERSION,
        flags,
        fname_len,
        filesize
    )

    checksum = zlib.crc32(filename_bytes + struct.pack(">Q", filesize)) & 0xFFFFFFFF
    return header_without_checksum + struct.pack(">I", checksum) + filename_bytes


def should_compress(file_path: str) -> bool:
    """
    Decide whether a file should be compressed.

    Args:
        file_path (str): Path to the file.

    Returns:
        bool: True if the file should be compressed, False otherwise.
    """
    file_path = os.path.abspath(file_path)

    if not os.path.isfile(file_path):
        return False

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    # Skip already compressed file types
    if ext in UNCOMPRESSIBLE_EXTS:
        return False

    return True

def compress_file(file_path, filename, filesize, logger, compress=True):
    temp_dir = None

    try:
        if compress:
            if not should_compress(file_path):
                logger.info("This file is already compressed, skipping compression")
                return file_path, filesize, False
            else:
                temp_dir = tempfile.mkdtemp()
                temp_path = os.path.join(temp_dir, filename + ".zlib")
                logger.info("Compressing file...")

                with open(file_path, "rb") as f_in, open(temp_path, "wb") as f_out:
                    compressor = zlib.compressobj(level=6)
                    while True:
                        try:
                            chunk = f_in.read(64 * 1024)
                            if not chunk:
                                break
                            f_out.write(compressor.compress(chunk))
                        except KeyboardInterrupt:
                            if temp_dir:
                                shutil.rmtree(temp_dir, ignore_errors=True)
                            raise

                    f_out.write(compressor.flush())

                old_filesize = filesize
                filesize = os.path.getsize(temp_path)
                logger.info(
                    f"Compressed '{filename}' from {format_bytes(old_filesize)} -> {format_bytes(filesize)}"
                )
                return temp_path, filesize, True
        else:
            return file_path, filesize, False

    except KeyboardInterrupt:
        # cleanup on user exit
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise  # bubble up so outer code can stop gracefully

    except Exception as e:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"Compression failed: {e}")
        raise


def send_file(file_path: str, host: str, port: int, logger, progress_bar: bool = False, name: str = None, compress: bool = false, rate_limit: int = 0):
    file_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(file_path):
        logger.error(f"File does not exist: {file_path}")
        sys.exit(1)

    filesize = os.path.getsize(file_path)
    filename = name or os.path.basename(file_path)
    flags = 0

    # Compress to temporary file if needed
    try:
        file_path, filesize, compressed = compress_file(file_path, filename, filesize, logger, compress)
        if compressed:
            flags |= transferflags.FLAG_COMPRESSED
    except Exception as e:
        logger.error(f"Compression failed: {e}\n")
        sys.exit(1)

    port = port or DEFAULT_PORT

    try:
        # --- secure connection with TOFU ---
        with secure.connect_with_tofu(host, port, logger) as ssock:

            logger.info(f"Secure connection to ('{host}', {port})")

            # Build and send header
            header = build_header(filename, filesize, flags=flags)
            ssock.sendall(header)

            logger.info(f"Sending '{filename}' ({format_bytes(filesize)}) from {file_path}")

            sent = send_linear(file_path, filesize, ssock, progress_bar, logger, rate_limit)

            if sent == 0:
                logger.error("No bytes were sent\n")
                sys.exit(1)

            # --- Wait for confirmation from receiver ---
            try:
                ack = ssock.recv(4)
                if ack != b"OKAY":
                    logger.error("Did not receive confirmation from receiver\n")
                    sys.exit(1)
            except Exception as e:
                logger.error(f"Failed to receive acknowledgment: {e}\n")
                sys.exit(1)

            logger.info(f"File sent successfully: {filename}")
            logger.info("Server connection closed\n")

    except KeyboardInterrupt as e:
        sys.exit(130)

    except Exception as e:
        logger.error(f"Error sending file: {e}\n")
        sys.exit(1)

import time

def send_linear(file_path, filesize, ssock, progress_bar, logger, rate_limit: int = 0):
    """
    Send file over the socket with optional bandwidth limiting.
    rate_limit: bytes per second. 0 = unlimited.
    """
    progress = tqdm(
        total=filesize,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        disable=not progress_bar,
        leave=False,
    )

    q = queue.Queue(maxsize=QUEUE_SIZE)
    stop_event = threading.Event()
    sent = 0
    start_time = time.time()
    bytes_sent_this_second = 0

    # ------------------------
    # Producer: read from SSD into RAM
    def reader():
        try:
            with open(file_path, "rb", buffering=FLUSH_SIZE) as f:
                while not stop_event.is_set():
                    data = f.read(FLUSH_SIZE)
                    if not data:
                        break
                    q.put(data)
        except Exception as e:
            logger.error(f"Reader error: {e}")
        finally:
            q.put(None)  # sentinel

    # ------------------------
    # Consumer: send from RAM to socket
    def sender():
        nonlocal sent, bytes_sent_this_second, start_time
        running = True
        next_send_time = time.time()
        try:
            while True:
                try:
                    data = q.get(timeout=0.5)
                except queue.Empty:
                    if stop_event.is_set():
                        break
                    continue

                if data is None:
                    break

                view = memoryview(data)
                while view and running:
                    chunk, view = view[:BUFFER_SIZE], view[BUFFER_SIZE:]
                    for attempt in range(MAX_SEND_RETRIES):
                        try:
                            ssock.sendall(chunk)
                            break
                        except (OSError, socket.error) as e:
                            if stop_event.is_set():
                                break
                            logger.warning(f"Send attempt {attempt + 1} failed: {e}")
                            time.sleep(1)
                    else:
                        stop_event.set()
                        logger.error("Failed to send chunk after retries")
                        running = False
                        continue

                    sent += len(chunk)
                    bytes_sent_this_second += len(chunk)
                    progress.update(len(chunk))

                    # ------------------------
                    # Bandwidth limiting
                    if rate_limit > 0:
                        # time we should finish sending this chunk
                        chunk_size = len(chunk)
                        target_time = chunk_size / rate_limit  # seconds

                        # next_send_time is initialized outside the loop as time.time()
                        now = time.time()
                        if now < next_send_time:
                            # sleep until it's time to send
                            remaining = next_send_time - now
                            interval = 0.01  # 10ms increments, interruptible
                            slept = 0
                            while slept < remaining:
                                if stop_event.is_set():
                                    break
                                sleep_chunk = min(interval, remaining - slept)
                                time.sleep(sleep_chunk)
                                slept += sleep_chunk

                        # update next allowed send time
                        next_send_time = max(now, next_send_time) + target_time


        except Exception as e:
            logger.error(f"Sender error: {e}")
            stop_event.set()

    # ------------------------
    # Launch threads
    t_reader = threading.Thread(target=reader, daemon=True)
    t_sender = threading.Thread(target=sender, daemon=True)

    t_reader.start()
    t_sender.start()

    # ------------------------
    # Wait until threads finish
    try:
        while t_reader.is_alive() or t_sender.is_alive():
            t_reader.join(timeout=0.5)
            t_sender.join(timeout=0.5)
    except KeyboardInterrupt:
        print('')
        stop_event.set()
        t_reader.join()
        t_sender.join()
        progress.close()
        sys.exit(130)

    progress.close()
    if stop_event.is_set():
        print('')
        progress.close()
        sys.exit(1)

    return sent


def cmd_send(args, logger):
    """Send a single file."""
    try:
        path = resolve_path(args.path)
    except Exception as e:
        logger.error(f"Error finding path: {e}\n")
        sys.exit(1)

    logger.debug(f"Preparing to send file '{path}' to {args.ip}")
    logger.debug(f"Options: {vars(args)}\n")

    limit = 0
    if args.limit:
        try:
            limit = parse_byte_string(args.limit)
        except Exception as e:
            logger.error(f"Error parsing limit: {e}\n")
            sys.exit(1)

    send_file(path, args.ip, args.port, logger, progress_bar=args.progress, name=args.name, compress=not args.nocompress, rate_limit=limit)


def cmd_send_dir(args, logger):
    """Send a directory by zipping it first."""
    try:
        path = resolve_path(args.path)
    except Exception as e:
        logger.error(f"Error finding path: {e}\n")
        sys.exit(1)

    logger.debug(f"Preparing to send directory '{path}' to {args.ip}")
    logger.debug(f"Options: {vars(args)}")

    try:
        zip_path = zip_directory(path, logger=logger, progress_bar=args.progress, force_python=args.pyzip)
        logger.info(f"Directory zipped successfully: {zip_path}\n")
    except (FileNotFoundError, NotADirectoryError, ValueError) as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

    if not args.name:
        name = os.path.basename(path)
    else:
        name = args.name

    limit = 0
    if args.limit:
        try:
            limit = parse_byte_string(args.limit)
        except Exception as e:
            logger.error(f"Error parsing limit: {e}\n")
            sys.exit(1)

    send_file(zip_path, args.ip, args.port, logger, progress_bar=args.progress, name=name, rate_limit=limit)

    # delete the temp zip after sending
    try:
        os.remove(zip_path)
        logger.debug(f"Temporary zip removed: {zip_path}")
    except Exception as e:
        logger.warning(f"Failed to remove temporary zip: {e}")

    print('')
