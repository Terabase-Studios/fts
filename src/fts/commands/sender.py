import logging
import os
import sys
import socket

from sympy import false

from fts.core.zipper import zip_directory
from fts.core import secure as secure
import struct
import zlib
import shutil
import tempfile
import time
import threading
import queue
from tqdm import tqdm
import zlib

import fts.flags

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
    logging.warning("Compression not implemented yet")

    try:
        if compress and False:
            if not should_compress(file_path):
                logger.info("This file is already compressed, skipping compression")
                return file_path, filesize
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
                return temp_path, filesize
        else:
            return file_path, filesize

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


def send_file(file_path: str, host: str, port: int, logger, progress_bar: bool = False, name: str = None, compress: bool = false) -> bytes:
    file_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(file_path):
        logger.error(f"File does not exist: {file_path}")
        sys.exit(1)

    filesize = os.path.getsize(file_path)
    filename = name or os.path.basename(file_path)
    flags = 0

    # Compress to temporary file if needed
    try:
        compress_file(file_path, filename, filesize, logger, compress)
        flags |= flags.FLAG_COMPRESSED
    except:
        print('')
        return bytes()

    port = port or DEFAULT_PORT

    try:
        # --- secure connection with TOFU ---
        with secure.connect_with_tofu(host, port, logger) as ssock:

            logger.info(f"Secure connection to ('{host}', {port})")

            # Build and send header
            header = build_header(filename, filesize, flags=flags)
            ssock.sendall(header)

            logger.info(f"Sending '{filename}' ({format_bytes(filesize)}) from {file_path}")

            sent = send_linear(file_path, filesize, ssock, progress_bar, logger)

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

def send_linear(file_path, filesize, ssock, progress_bar, logger):
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

    # ------------------------
    # Producer: read from SSD into RAM
    def reader():
        try:
            with open(file_path, "rb", buffering=FLUSH_SIZE) as f:
                while not stop_event.is_set():
                    data = f.read(FLUSH_SIZE)
                    if not data:
                        break
                    q.put(data)  # blocks if queue is full
        except Exception as e:
            logger.error(f"Reader error: {e}")
        finally:
            q.put(None)  # sentinel for end-of-file

    # ------------------------
    # Consumer: send from RAM to socket
    def sender():
        nonlocal sent
        running = True
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
                    progress.update(len(chunk))

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
    # Wait until threads finish, handle Ctrl+C
    try:
        while t_reader.is_alive() or t_sender.is_alive():
            t_reader.join(timeout=0.5)
            t_sender.join(timeout=0.5)
    except KeyboardInterrupt:
        print('')
        stop_event.set()
        # Wait briefly for threads to exit
        t_reader.join()
        t_sender.join()
        progress.close()
        sys.exit(130)

    progress.close()
    if stop_event.is_set():
        # If any thread signaled stop due to error, exit here
        print('')
        progress.close()
        sys.exit(1)

    return sent


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    power = 1024
    n = 0
    s = float(size)

    while s >= power and n < len(units) - 1:
        s /= power
        n += 1

    return f"{s:.2f} {units[n]}"


def cmd_send(args, logger):
    """Send a single file."""
    try:
        path = resolve_path(args.path)
    except Exception as e:
        logger.error(f"Error finding path: {e}\n")
        sys.exit(1)

    logger.debug(f"Preparing to send file '{path}' to {args.ip}")
    logger.debug(f"Options: {vars(args)}\n")

    send_file(path, args.ip, args.port, logger, progress_bar=args.progress, name=args.name, compress=not args.nocompress)


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
        name = os.path.basename(zip_path).removesuffix(".zip")
    else:
        name = args.name

    send_file(zip_path, args.ip, args.port, logger, progress_bar=args.progress, name=name)

    # delete the temp zip after sending
    try:
        os.remove(zip_path)
        logger.debug(f"Temporary zip removed: {zip_path}")
    except Exception as e:
        logger.warning(f"Failed to remove temporary zip: {e}")

    print('')
