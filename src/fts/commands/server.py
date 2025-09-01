import os
import sys
import socket
import zipfile
import threading
import zlib
import struct
from fts.core import secure as secure
from tqdm import tqdm
import math
from fts.config import (
    DEFAULT_PORT,
    MAGIC,
    VERSION,
    BUFFER_SIZE,
)

def cmd_open(args, logger, shutdown_event=None):
    """Start TLS receiver server safely with dynamic port handling."""
    logger.debug(f"Preparing to open server")
    logger.debug(f"Options: {vars(args)}\n")

    host = args.ip or '0.0.0.0'
    output_dir = os.path.abspath(args.output or ".")
    os.makedirs(output_dir, exist_ok=True)

    # Determine port (0 = let OS pick free port)
    port = args.port or DEFAULT_PORT

    # Prepare TLS context (certs created if missing)
    context = secure.get_server_context()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Retry binding if port is taken
        for attempt in range(5):
            try:
                sock.bind((host, port))
                break
            except OSError as e:
                if port != 0:
                    logger.warning(f"Port {port} unavailable, retrying with free port...")
                    port = 0
                else:
                    logger.error(f"Failed to bind socket: {e}")
                    raise
        else:
            logger.error("Could not bind socket after 5 attempts.")
            sys.exit(1)

        port = sock.getsockname()[1]  # actual port used
        sock.listen(5)
        logger.info(f"Receiver listening on {host}:{port}, saving to {output_dir}\n")

        sock.settimeout(1.0)  # allows periodic shutdown check

        try:
            while True:
                if shutdown_event and shutdown_event.is_set():
                    logger.info("Shutdown signal received. Exiting server.")
                    break

                try:
                    client_sock, addr = sock.accept()
                    try:
                        # Upgrade raw TCP socket to TLS
                        ssock = context.wrap_socket(client_sock, server_side=True)
                        logger.info(f"Secure connection from {addr}")
                        threading.Thread(
                            target=_handle_client,
                            args=(ssock, output_dir, logger, args.extract, args.progress, host, port),
                            daemon=True
                        ).start()
                    except Exception as e:
                        logger.error(f"TLS handshake failed from {addr}: {e}")
                        client_sock.close()
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Accept error: {e}, continuing to listen...")
                    continue
        except KeyboardInterrupt:
            sys.exit(130)
        except Exception as e:
            logger.critical(f"Server error: {e}")


def _handle_client(ssock, output_dir, logger, extract, progress, host=None, port=None):
    """
    Handle a single client in a separate thread safely.
    Automatically closes the socket and cleans up progress bar.
    """
    try:
        receive_file(ssock, output_dir, logger, extract, progress_bar=progress)

    except Exception as e:
        logger.error(f"Client handling error: {e}")

    finally:
        # Ensure socket is closed
        try:
            ssock.close()
        except Exception:
            pass

        # Log connection closed
        logger.info("Client connection closed\n")

        # Log listening status if host and port are provided
        if host and port:
            logger.info(f"Receiver listening on {host}:{port}, saving to {output_dir}\n")


def parse_header(ssock):
    """Receive and parse structured header from socket."""
    # Fixed header size: 4s (magic) + f (4) + B (1) + H (2) + Q (8) + I (4)
    fixed_header_size = 4 + 4 + 1 + 2 + 8 + 4
    header = b""
    while len(header) < fixed_header_size:
        chunk = ssock.recv(fixed_header_size - len(header))
        if not chunk:
            raise ConnectionError("Connection closed while receiving header")
        header += chunk

    try:
        # Unpack: magic, version, flags, fname_len, filesize, checksum
        magic, version, flags, fname_len, filesize = struct.unpack(">4sfBHQ", header[:19])
        checksum = struct.unpack(">I", header[19:23])[0]
    except Exception as e:
        raise ValueError(f"Failed to unpack header: {e}")

    if magic != MAGIC:
        raise ValueError(f"Invalid magic number: {magic}")
    if not math.isclose(version, VERSION, rel_tol=1e-6):
        raise ValueError(f"Incompatible version: {version}")

    # Receive filename
    filename_bytes = b""
    while len(filename_bytes) < fname_len:
        chunk = ssock.recv(fname_len - len(filename_bytes))
        if not chunk:
            raise ConnectionError("Connection closed while receiving filename")
        filename_bytes += chunk

    # Validate checksum
    calc_checksum = zlib.crc32(filename_bytes + struct.pack(">Q", filesize)) & 0xFFFFFFFF
    if calc_checksum != checksum:
        raise ValueError("Header checksum mismatch")

    filename = os.path.basename(filename_bytes.decode("utf-8"))
    return filename, filesize, flags


def receive_file(ssock, output_dir, logger, extract=False, progress_bar: bool = False):
    """Receive a file from a TLS socket with structured header and safe logging."""
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Parse structured header
    try:
        filename, filesize, flags = parse_header(ssock)
    except Exception as e:
        logger.error(f"Failed to parse header: {e}")
        return  # exit early if header invalid

    out_path = os.path.join(output_dir, filename)
    logger.info(f"Receiving '{filename}' ({filesize} bytes) into {output_dir}")

    received = 0
    progress = tqdm(
        total=filesize,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        disable=not progress_bar,
        leave=False,
    )

    try:
        with open(out_path, "wb") as f:
            while received < filesize:
                try:
                    chunk = ssock.recv(min(BUFFER_SIZE, filesize - received))
                except Exception as e:
                    logger.error(f"Error receiving data: {e}")
                    break

                if not chunk:
                    # Connection closed by peer
                    logger.warning(
                        f"Connection closed before full file received ({received}/{filesize} bytes)"
                    )
                    break

                f.write(chunk)
                received += len(chunk)
                progress.update(len(chunk))


    except Exception as e:
        logger.error(f"Error writing file: {e}")
        return

    progress.close()

    # Final check after loop
    if received < filesize:
        logger.warning(f"Incomplete file received ({received}/{filesize} bytes of {filesize})")
        return

    else:
        logger.info(f"File received successfully: {filename}")
        logger.debug(f"File saved: {out_path}")
        try:
            logger.debug(f"Sending acknowledgement")
            ssock.sendall(b"OKAY")
        except Exception as e:
            logger.warning(f"Failed to send acknowledgment: {e}")

    # Optional extraction for zip files
    if extract and zipfile.is_zipfile(out_path):
        try:
            # Ensure the file ends with .zip
            if not out_path.lower().endswith(".zip"):
                new_out_path = out_path + ".zip"
                try:
                    os.rename(out_path, new_out_path)
                    logger.debug(f"Renamed file to have .zip extension: {new_out_path}")
                    out_path = new_out_path
                    filename = os.path.basename(out_path)  # refresh filename
                except Exception as e:
                    logger.warning(f"Failed to rename file to .zip: {e}")

            # Temporary extraction path
            extract_path = os.path.join(output_dir, os.path.splitext(filename)[0] + "_extracting")
            os.makedirs(extract_path, exist_ok=True)

            # Final target name (same as zip, without .zip extension)
            final_path = os.path.join(output_dir, os.path.splitext(filename)[0])

            logger.info(f"Extracting zip to {final_path}")
            with zipfile.ZipFile(out_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

            # Delete the original zip
            try:
                os.remove(out_path)
                logger.debug(f"Original zip removed: {out_path}")
            except Exception as e:
                logger.warning(f"Failed to remove original zip: {e}")

            # Rename extracted folder
            os.rename(extract_path, final_path)
            logger.debug(f"Renamed extracted folder to: {final_path}")

            logger.info("Extracted zip")

        except Exception as e:
            logger.error(f"Zip extraction error: {e}")


def cmd_close(args, logging):
    pass