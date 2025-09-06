import os
import queue
import shutil
import socket
import struct
import sys
import tempfile
import asyncio
import time
import aiofiles
import threading
import zlib

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


async def send_file(
    file_path: str,
    host: str,
    port: int,
    logger,
    progress_bar: bool = False,
    name: str = None,
    compress: bool = False,
    rate_limit: int = 0,
):
    """
    Asynchronously send a file over a secure socket with optional compression and rate limiting.
    """

    file_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(file_path):
        logger.error(f"File does not exist: {file_path}")
        sys.exit(1)

    filesize = os.path.getsize(file_path)
    filename = name or os.path.basename(file_path)
    flags = 0

    # Compress if requested
    try:
        file_path, filesize, compressed = compress_file(
            file_path, filename, filesize, logger, compress
        )
        if compressed:
            flags |= transferflags.FLAG_COMPRESSED
    except Exception as e:
        logger.error(f"Compression failed: {e}\n")
        sys.exit(1)

    port = port or DEFAULT_PORT

    try:
        # --- secure connection with TOFU ---
        ssl_context = await asyncio.to_thread(secure.connect_with_tofu, host, port, logger)
        reader, writer = await asyncio.open_connection(host, port, ssl=ssl_context, server_hostname=host)

        logger.info(f"Secure connection to ('{host}', {port})")

        # Build and send header
        header = build_header(filename, filesize, flags=flags)
        writer.write(header)
        await writer.drain()

        logger.info(f"Sending '{filename}' ({format_bytes(filesize)}) from {file_path}")

        # Send file using asyncio-based pipeline
        sent = await send_linear(file_path, filesize, writer, progress_bar, logger, rate_limit)

        if sent < filesize:
            logger.error("Not all bytes were sent")
            return

        # --- Wait for confirmation ---
        try:
            ack = await reader.readexactly(4)
            if ack != b"OKAY":
                logger.error("Did not receive confirmation from receiver")
                sys.exit(1)

            logger.info(f"File sent successfully: {filename}")
        except:
            logger.warning("Confirmation failed")

        logger.info("Server connection closed")
        writer.close()


    except asyncio.CancelledError:
        raise KeyboardInterrupt
    except Exception as e:
        logger.error(f"Error sending file: {e}\n")
        sys.exit(1)


async def send_linear(file_path, filesize, writer, progress_bar, logger, rate_limit: int = 0):
    """
    Async file sender with cooperative rate limiting using StreamWriter.
    """
    progress = tqdm(
        total=filesize,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        disable=not progress_bar,
        leave=False,
    )

    sent = 0
    next_send_time = time.monotonic()

    try:
        async with aiofiles.open(file_path, "rb") as f:
            while True:
                data = await f.read(FLUSH_SIZE)
                if not data:
                    break

                view = memoryview(data)
                while view:
                    chunk, view = view[:BUFFER_SIZE], view[BUFFER_SIZE:]

                    writer.write(chunk)
                    await writer.drain()

                    sent += len(chunk)
                    progress.update(len(chunk))

                    # --- Bandwidth limiting ---
                    if rate_limit > 0:
                        target_time = len(chunk) / rate_limit
                        now = time.monotonic()
                        if now < next_send_time:
                            await asyncio.sleep(next_send_time - now)
                        next_send_time = max(now, next_send_time) + target_time

    except asyncio.CancelledError:
        progress.close()
        raise asyncio.CancelledError
    except Exception as e:
        progress.close()
        logger.error(f"Error while sending file: {e}")
    finally:
        progress.close()

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

    try:
        asyncio.run(send_file(path, args.ip, args.port, logger, progress_bar=args.progress, name=args.name, compress=not args.nocompress, rate_limit=limit))
    except KeyboardInterrupt:
        logger.error("User interrupt")


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

    try:
        asyncio.run(send_file(zip_path, args.ip, args.port, logger, progress_bar=args.progress, name=name, rate_limit=limit))
    except KeyboardInterrupt:
        logger.error("User interrupt")

    # delete the temp zip after sending
    try:
        os.remove(zip_path)
        logger.debug(f"Temporary zip removed: {zip_path}")
    except Exception as e:
        logger.warning(f"Failed to remove temporary zip: {e}")
