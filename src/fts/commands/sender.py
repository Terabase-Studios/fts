import asyncio
import os
import shutil
import struct
import tempfile
import time
import zlib
from ssl import SSLError

from tqdm.asyncio import tqdm_asyncio as tqdm

import fts.flags as transferflags
from fts.config import (
    DEFAULT_FILE_PORT,
    MAGIC,
    VERSION,
    BUFFER_SIZE,
    FLUSH_SIZE,
    BATCH_SIZE,
    PROGRESS_INTERVAL,
    UNCOMPRESSIBLE_EXTS,
)
from fts.core import secure as secure
from fts.utilities import format_bytes, parse_byte_string

def cmd_send(args, logger):
    """Send a single file."""
    try:
        path = resolve_path(args.path)
    except Exception as e:
        logger.error(f"Error finding path: {e}\n")
        return

    logger.info(f"Preparing to send file '{path}' to {args.ip}")
    logger.debug(f"Options: {vars(args)}\n")

    limit = 0
    if args.limit:
        try:
            limit = parse_byte_string(args.limit)
        except Exception as e:
            logger.error(f"Error parsing limit: {e}\n")
            return

    try:
        asyncio.run(send_file(path, args.ip, args.port, logger, progress_bar=args.progress, name=args.name, compress=not args.nocompress, rate_limit=limit))
    except KeyboardInterrupt:
        logger.error("User interrupt")

# -------------------------
# Helper functions
# -------------------------
def resolve_path(path: str) -> str:
    if not path or path == "":
        raise ValueError("No path given")
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
        return

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
        return

    port = port or DEFAULT_FILE_PORT

    try:
        # --- secure connection with TOFU ---
        reader, writer = await secure.connect_with_tofu_async(host, port, logger)
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
                return

            logger.info(f"File sent successfully: {filename}")
        except:
            logger.warning("Confirmation failed")

        logger.info(f"Secure connection to ('{host}', {port}) closed")
        writer.close()


    except asyncio.CancelledError:
        raise KeyboardInterrupt
    except Exception as e:
        logger.error(f"Error sending file: {e}\n")
        return


async def send_linear(file_path, filesize, writer, progress_bar, logger, rate_limit: int = 0):
    """
    Ultra-fast async file sender using thread-based blocking file reads.
    Avoids blocking event loop and unnecessary memory copies.
    """

    loop = asyncio.get_running_loop()
    old_handler = loop.get_exception_handler()

    def quiet_handler(loop, context):
        if "SL connection is closed" in str(context.get("exception")):
            return  # swallow the spam
        if old_handler is not None:
            old_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(quiet_handler)

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
    last_progress_update = time.monotonic()
    start_time = 0
    end_time = 0

    # Helper function to read a chunk in a thread
    def read_chunk(f, size):
        return f.read(size)

    try:
        start_time = time.monotonic()
        with open(file_path, "rb") as f:  # regular blocking file
            while True:
                # Read a large chunk in a thread to avoid blocking event loop
                chunk = await asyncio.to_thread(read_chunk, f, BUFFER_SIZE * BATCH_SIZE)
                if not chunk:
                    break

                mv = memoryview(chunk)
                batch_size_bytes = len(mv)

                writer.write(mv)

                # Bandwidth limiting
                if rate_limit > 0:
                    now = time.monotonic()
                    target_time = batch_size_bytes / rate_limit
                    if now < next_send_time:
                        await asyncio.sleep(next_send_time - now)
                    next_send_time = max(now, next_send_time) + target_time

                sent += batch_size_bytes

                # Only drain if buffer is large
                if writer.transport.get_write_buffer_size() > FLUSH_SIZE:
                    await writer.drain()
                    pass

                # Update progress periodically
                now = time.monotonic()
                if progress_bar and now - last_progress_update >= PROGRESS_INTERVAL:
                    progress.n = sent
                    progress.refresh()
                    last_progress_update = now

        # Final drain
        await writer.drain()
        if progress_bar:
            progress.n = sent
            progress.refresh()

        end_time = time.monotonic()

    except asyncio.CancelledError:
        raise
    except (ConnectionResetError, BrokenPipeError) as e:
        if sent < filesize:
            logger.error(f"Connection closed: {e}")
            raise
    except SSLError as e:
        logger.error(f"SSL connection closed: {e}")
        raise
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        raise
    except Exception as e:
        logger.error(f"{e}")
        raise
    finally:
        duration = end_time - start_time
        progress.close()
        loop.set_exception_handler(old_handler)
        logger.debug(f"Transferred {format_bytes(sent)} in {duration:.2f} seconds: ({format_bytes(sent/duration)}/s)")
        return sent