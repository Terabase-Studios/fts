import os
import sys
import socket
from fts.core.zipper import zip_directory
from fts.core import secure as secure
import struct
import zlib
import time
from tqdm import tqdm

from fts.config import (
    DEFAULT_PORT,
    MAGIC,
    VERSION,
    BUFFER_SIZE,
    MAX_SEND_RETRIES,
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


def send_file(file_path: str, host: str, port: int, logger, progress_bar: bool = False, name: str = None) -> bytes:
    file_path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(file_path):
        logger.error(f"File does not exist: {file_path}")
        sys.exit(1)

    filesize = os.path.getsize(file_path)
    filename = name or os.path.basename(file_path)
    port = port or DEFAULT_PORT

    try:
        # --- secure connection with TOFU ---
        with secure.connect_with_tofu(host, port, logger) as ssock:

            logger.info(f"Secure connection to ('{host}', {port})")

            # Build and send header
            header = build_header(filename, filesize)
            ssock.sendall(header)

            logger.info(f"Sending '{filename}' ({filesize} bytes) from {file_path}")

            # Send file in chunks with retries
            sent = 0
            progress = tqdm(
                total=filesize,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                disable=not progress_bar,
                leave=False,
            )

            with open(file_path, "rb") as f:
                while chunk := f.read(BUFFER_SIZE):
                    for attempt in range(MAX_SEND_RETRIES):
                        try:
                            ssock.sendall(chunk)
                            break

                        except (OSError, socket.error) as e:
                            logger.warning(f"Send attempt {attempt+1} failed: {e}")
                            time.sleep(1)
                    else:
                        progress.close()
                        logger.error("Failed to send chunk after retries\n")
                        sys.exit(1)

                    sent += len(chunk)
                    progress.update(len(chunk))

            progress.close()

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


def cmd_send(args, logger):
    """Send a single file."""
    path = resolve_path(args.path)
    logger.debug(f"Preparing to send file '{path}' to {args.ip}")
    logger.debug(f"Options: {vars(args)}\n")

    send_file(path, args.ip, args.port, logger, progress_bar=args.progress, name=args.name)


def cmd_send_dir(args, logger):
    """Send a directory by zipping it first."""
    path = resolve_path(args.path)
    logger.debug(f"Preparing to send directory '{path}' to {args.ip}")
    logger.debug(f"Options: {vars(args)}")

    try:
        zip_path = zip_directory(path, logger=logger, progress_bar=args.progress, force_python=args.py_zip)
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
