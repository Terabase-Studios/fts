import os
import sys
import socket
import zipfile
import threading
import zlib
import struct
from fts.core import secure as secure
from tqdm import tqdm
import time
import shutil
import subprocess
import psutil
from fts.config import (
    DEFAULT_PORT,
    MAGIC,
    VERSION,
    BUFFER_SIZE,
    PID_FILE,
)


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
    startupinfo = subprocess.STARTUPINFO() if os.name == "nt" else None
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
        print('')
        return

    host = args.ip or '0.0.0.0'
    output_dir = os.path.abspath(args.output or ".")
    os.makedirs(output_dir, exist_ok=True)

    port = args.port or DEFAULT_PORT
    context = secure.get_server_context()

    shutdown_event = threading.Event()

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
            logger.critical("Could not bind socket after 5 attempts.")
            sys.exit(1)

        port = sock.getsockname()[1]
        sock.listen(5)
        sock.settimeout(1.0)
        logger.info(f"Receiver listening on {host}:{port}, saving to {output_dir}\n")

        # ------------------------
        # Main server loop
        try:
            while not shutdown_event.is_set():
                try:
                    client_sock, addr = sock.accept()
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Accept error: {e}")
                    continue

                # ------------------------
                # Wrap TLS and start handler thread
                try:
                    ssock = context.wrap_socket(client_sock, server_side=True)
                    ssock.settimeout(1.0)
                    logger.info(f"Secure connection from {addr}")

                    threading.Thread(
                        target=_handle_client,
                        args=(ssock, output_dir, logger, args.extract, args.progress, host, port, shutdown_event),
                        daemon=True
                    ).start()

                except Exception as e:
                    logger.error(f"TLS handshake failed from {addr}: {e}")
                    client_sock.close()

        except KeyboardInterrupt:
            shutdown_event.set()
            time.sleep(1)
        except Exception as e:
            logger.critical(f"Server error: {e}")


def _handle_client(ssock, output_dir, logger, extract, progress, host=None, port=None, stop_event=None):
    try:
        if stop_event and stop_event.is_set():
            logger.info("Stop event set, skipping client.")
            return

        receive_file(
            ssock, output_dir, logger,
            extract, progress_bar=progress,
            stop_event=stop_event
        )

    except Exception as e:
        logger.error(f"Client handling error: {e}")

    finally:
        try:
            ssock.close()
        except Exception:
            pass

        logger.info("Client connection closed\n")

        if host and port and (not stop_event or not stop_event.is_set()):
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
    if int(VERSION*1000) != int(version*1000):
        raise ValueError(f"Incompatible version( Server{VERSION} | Sender: {version} )")

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


def receive_file(ssock, output_dir, logger, extract=False, progress_bar: bool = False, stop_event=None):
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Parse header
    try:
        filename, filesize, flags = parse_header(ssock)
    except Exception as e:
        logger.error(f"Failed to parse header: {e}")
        return

    out_path = os.path.join(output_dir, filename)
    logger.info(f"Receiving '{filename}' ({format_bytes(filesize)}) into {output_dir}")

    received = receive_linear(out_path, filesize, ssock, progress_bar, logger, stop_event=stop_event)

    if received < filesize or (stop_event and stop_event.is_set()):
        logger.warning(f"Incomplete file received ({format_bytes(received)}/{format_bytes(filesize)} bytes of {filename})")
        if os.path.exists(out_path):
            os.remove(out_path)
        return

    logger.info(f"File received successfully: {filename}")

    try:
        ssock.sendall(b"OKAY")
    except Exception as e:
        logger.warning(f"Failed to send acknowledgment: {e}")

    # Optional extraction
    if extract and zipfile.is_zipfile(out_path):
        try:
            extract_path = os.path.join(output_dir, os.path.splitext(filename)[0] + "_extracting")
            os.makedirs(extract_path, exist_ok=True)
            final_path = os.path.join(output_dir, os.path.splitext(filename)[0])

            logger.info(f"Extracting zip to {final_path}")
            with zipfile.ZipFile(out_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

            try: os.remove(out_path)
            except Exception as e: logger.warning(f"Failed to remove original zip: {e}")

            os.rename(extract_path, final_path)
            logger.info("Extracted zip")
        except Exception as e:
            logger.error(f"Zip extraction error: {e}")


def receive_linear(out_path, filesize, ssock, progress_bar, logger, stop_event=None):
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
                if stop_event and stop_event.is_set():
                    break

                try:
                    chunk = ssock.recv(min(BUFFER_SIZE, filesize - received))
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error receiving data: {e}")
                    break

                if not chunk:
                    logger.warning(f"Connection closed before full file received ({received}/{filesize} bytes)")
                    break

                f.write(chunk)
                received += len(chunk)
                progress.update(len(chunk))

    finally:
        progress.close()
        if not os.path.exists(out_path):
            os.remove(out_path)

    return received

def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    power = 1024
    n = 0
    s = float(size)

    while s >= power and n < len(units) - 1:
        s /= power
        n += 1

    return f"{s:.2f} {units[n]}"


def cmd_close(args, logger):
    """
    Stops the detached FTS server if it's running.
    """
    if not os.path.exists(PID_FILE):
        logger.warning("No PID file found, server may not be running.\n")
        return

    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except Exception as e:
        logger.error(f"Failed to read PID file: {e}\n")
        return

    if not psutil.pid_exists(pid):
        logger.warning(f"No process with PID {pid} found. Removing stale PID file.\n")
        os.remove(PID_FILE)
        return

    try:
        proc = psutil.Process(pid)
        logger.info(f"Stopping server (PID {pid})")
        logger.debug(f"cmd: {' '.join(proc.cmdline())}")
        proc.terminate()  # send SIGTERM on Unix / terminate on Windows
        try:
            proc.wait(timeout=5)  # wait up to 5 seconds
            logger.info("Server stopped successfully.\n")
        except psutil.TimeoutExpired:
            logger.warning("Server did not stop in time. Killing forcibly.\n")
            proc.kill()
        os.remove(PID_FILE)
    except Exception as e:
        logger.error(f"Failed to stop server PID {pid}: {e}\n")
