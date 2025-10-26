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
    MAX_SEND_RETRIES
)
from fts.core import secure as secure
from fts.manager import Manager
from fts.utilities import format_bytes, parse_byte_string


def cmd_send(args, logger, manager=None):
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
        asyncio.run(send_file(path, args.ip, args.port, logger, progress_bar=args.progress, name=args.name, compress=not args.nocompress, rate_limit=limit, manager=manager))
    except KeyboardInterrupt:
        raise KeyboardInterrupt

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
    if fname_len > 1024:
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
    manager: Manager = None
):
    """
    Asynchronously send a file over a secure socket with optional compression and rate limiting.
    """
    if manager:
        if manager.in_use:
            manager = None
            logger.warning("Cannot use the same manager twice!\n Detaching manager")
        else:
            manager.in_use = True
            manager.type = "send"

    if manager:
        manager.state = "starting"
        if manager.cancelled:
            logger.error("Manager cancelled transfer")
            return

    file_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(file_path):
        logger.error(f"File does not exist: {file_path}")
        return

    filesize = os.path.getsize(file_path)
    filename = name or os.path.basename(file_path)
    flags = 0
    if manager:
        manager.max_progress = filesize
        if manager.cancelled:
            logger.error("Manager cancelled transfer")
            return

    # Compress if requested
    try:
        if manager:
            manager.state = "compressing"
            if manager.cancelled:
                logger.error("Manager cancelled transfer")
                return
        file_path, filesize, compressed = compress_file(
            file_path, filename, filesize, logger, compress
        )
        if compressed:
            flags |= transferflags.FLAG_COMPRESSED
    except Exception as e:
        logger.error(f"Compression failed: {e}\n")
        if manager:
            manager.state = "failed"
        return

    port = port or DEFAULT_FILE_PORT

    try:
        # --- secure connection with TOFU ---
        reader, writer = await connect_with_retry(host, port, logger, retries=MAX_SEND_RETRIES)

        logger.info(f"Secure connection to ('{host}', {port})")

        # Build and send header
        header = build_header(filename, filesize, flags=flags)
        writer.write(header)
        await writer.drain()

        logger.info(f"Sending '{filename}' ({format_bytes(filesize)}) from {file_path}")
        logger.debug(f"Awaiting server approval")
        if manager:
            if manager.cancelled:
                logger.error("Manager cancelled transfer")
                return
            manager.state = "transferring"
        while True:
            try:
                ack = await reader.readexactly(4)
                if ack == b"HOLD":
                    logger.info("Transfer on hold, the transfer will continue when server is ready")
                    if manager:
                        if manager.cancelled:
                            logger.error("Manager cancelled transfer")
                            return
                        manager.state = "hold"
                elif ack != b"SEND":
                    logger.error("Send request denied by receiver")
                    if manager:
                        manager.state = "failed"
                    return
                else:
                    break

            except:
                logger.error("Failed to recieve permission from receiver")
                if manager:
                    manager.state = "failed"
                return

        logger.debug(f"Successfully received server permission")

        # Send file using asyncio-based pipeline
        sent = await send_linear(file_path, filesize, writer, progress_bar, logger, rate_limit, manager=manager)

        if sent < filesize:
            logger.warning("Not all bytes were sent")
            if manager:
                manager.state = "failed"
                if manager.cancelled:
                    logger.error("Manager cancelled transfer")
                    raise Exception("Manager cancelled transfer")
            return

        # --- Wait for confirmation ---
        try:
            ack = await reader.readexactly(4)
            if ack != b"OKAY":
                logger.error("Did not receive confirmation from receiver")
                if manager:
                    manager.state = "failed"
                return

            logger.info(f"File sent successfully: {filename}")
        except:
            logger.warning("Transfer confirmation from receiver failed")

        logger.info(f"Secure connection to ('{host}', {port}) closed")
        writer.close()
        if manager:
            manager.progress = sent
            manager.state = "finished"


    except asyncio.CancelledError:
        if manager:
            manager.state = "failed"
        raise KeyboardInterrupt
    except Exception as e:
        logger.error(f"Error sending file: {e}\n")
        if manager:
            manager.state = "failed"
        return


async def connect_with_retry(host, port, logger, retries: int = 5, delay: int = 3):
    for attempt in range(1, retries + 1):
        try:
            reader, writer = await secure.connect_with_tofu_async(host, port, logger)
            return reader, writer  # success!
        except Exception as e:
            logger.error(f"Connection attempt {attempt} failed: {e}")
            if attempt < retries:
                logger.info(f"Retrying in {delay} seconds...\n")
                await asyncio.sleep(delay)
            else:
                raise
    return None, None


async def send_linear(file_path, filesize, writer, progress_bar, logger, rate_limit: int = 0, manager: Manager = None):
    """
    Ultra-fast async file sender using thread-based blocking file reads.
    Avoids blocking event loop and unnecessary memory copies.
    Gracefully handles receiver disconnects.
    """

    loop = asyncio.get_running_loop()
    old_handler = loop.get_exception_handler()

    def quiet_handler(loop, context):
        exc = context.get("exception")
        msg = str(exc or context.get("message", ""))
        if any(s in msg for s in ("SSL connection is closed", "Transport is closed", "Connection reset")):
            # swallow harmless post-shutdown spam
            return
        if old_handler:
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
    start_time = time.monotonic()
    end_time = start_time

    def read_chunk(f, size):
        return f.read(size)

    try:
        with open(file_path, "rb") as f:
            while True:
                chunk = await asyncio.to_thread(read_chunk, f, BUFFER_SIZE * BATCH_SIZE)
                if not chunk:
                    break

                try:
                    writer.write(chunk)
                except (ConnectionResetError, BrokenPipeError, SSLError):
                    logger.warning("Receiver disconnected during send.")
                    break

                if manager and manager.cancelled:
                    logger.error("Manager cancelled transfer")
                    raise Exception("Manager cancelled transfer")

                # Bandwidth limiting
                if rate_limit > 0:
                    now = time.monotonic()
                    target_time = len(chunk) / rate_limit
                    if now < next_send_time:
                        await asyncio.sleep(next_send_time - now)
                    next_send_time = max(now, next_send_time) + target_time

                sent += len(chunk)

                # Drain only if buffer is large
                if writer.transport.is_closing():
                    logger.error("Disconnected from receiver")
                    break
                if writer.transport.get_write_buffer_size() > FLUSH_SIZE:
                    try:
                        await writer.drain()
                    except (ConnectionResetError, BrokenPipeError, SSLError):
                        logger.warning("Drain failed: receiver closed connection.")
                        break

                # Update progress periodically
                now = time.monotonic()
                if progress_bar and now - last_progress_update >= PROGRESS_INTERVAL:
                    progress.n = sent
                    progress.refresh()
                    if manager:
                        if manager.cancelled:
                            logger.error("Manager cancelled transfer")
                            raise Exception("Manager cancelled transfer")
                        manager.progress = sent
                    last_progress_update = now

        # Final drain, safely
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError, SSLError):
            pass

        if progress_bar:
            progress.n = sent
            progress.refresh()
            if manager:
                manager.progress = sent

        end_time = time.monotonic()

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error in send_linear: {e}")
        raise
    finally:
        progress.close()
        loop.set_exception_handler(old_handler)
        duration = max(0.001, end_time - start_time)
        logger.debug(f"Transferred {format_bytes(sent)} in {duration:.2f}s ({format_bytes(sent/duration)}/s)")
        return sent