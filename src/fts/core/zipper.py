import datetime
import os
import re
import subprocess
import sys
import tempfile
import zipfile

from tqdm import tqdm


def zip_directory(directory_path, zip_name=None, logger=None, quiet=False, progress_bar=False, force_python=False):
    """
    Create a zip archive of a directory in the system temp dir and return its path.
    Shows a progress bar per directory if progress_bar=True.
    Logs permission errors in a unified format: Permission denied [full_path]
    """

    zip_path = _prepare_zip_path(directory_path, zip_name)
    log_permission = lambda path: _log_permission(path, logger, quiet)

    # Try native zipping first
    if force_python or not _try_native_zip(directory_path, zip_path, logger, quiet, log_permission):
        # Fallback to Python zipfile
        _zip_with_python(directory_path, zip_path, progress_bar, logger, quiet, log_permission)

    return zip_path


# ---------------- Helper Functions ---------------- #

def _prepare_zip_path(directory_path, zip_name):
    """Verify directory and generate unique zip path."""
    if not os.path.exists(directory_path):
        raise FileNotFoundError(f"Path does not exist: {directory_path}")
    if not os.path.isdir(directory_path):
        raise NotADirectoryError(f"Not a directory: {directory_path}")
    if not any(os.scandir(directory_path)):
        raise ValueError(f"Directory is empty: {directory_path}")

    if zip_name is None:
        base = os.path.basename(os.path.normpath(directory_path))
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"{base}_{timestamp}.zip"

    return os.path.join(tempfile.gettempdir(), zip_name)


def _log_permission(path, logger, quiet):
    """Log a permission denied message in a consistent format."""
    msg = f"Permission denied [{path}]"
    if logger:
        logger.warning(msg)
    elif not quiet:
        print(msg)


def _try_native_zip(directory_path, zip_path, logger, quiet, log_permission):
    """Attempt native zipping. Returns True only if archive is valid."""
    try:
        if sys.platform.startswith("win"):
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                f"try {{ Compress-Archive -Path '{directory_path}\\*' -DestinationPath '{zip_path}' -CompressionLevel Fastest -Force }} "
                f"catch {{ $_.Exception.Message }}"
            ]
            if logger: logger.info("Zipping via PowerShell Compress-Archive")
            result = subprocess.run(cmd, capture_output=True, text=True)
            _handle_windows_native_errors(result, log_permission)

        else:
            cmd = ['zip', '-r', '-1', zip_path, directory_path]
            if logger: logger.info("Zipping via native zip command")
            result = subprocess.run(cmd, capture_output=True, text=True)
            _handle_unix_native_errors(result, cmd, log_permission)

        # Verify archive actually exists & is non-empty
        if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
            return True
        else:
            raise RuntimeError("Native zip produced no output")

    except Exception as e:
        if logger:
            logger.warning(f"Native zip failed ({e}), falling back to Python zipfile")
        elif not quiet:
            print(f"Native zip failed ({e}), falling back to Python zipfile")
        return False


def _handle_windows_native_errors(result, log_permission):
    """Parse PowerShell Compress-Archive errors for permission messages."""
    try:
        for line in (result.stdout + result.stderr).splitlines():
            if "Access to the path" in line:
                match = re.search(r"'(.+?)'", line)
                path = match.group(1) if match else "unknown"
                log_permission(path)
    except KeyboardInterrupt:
        raise

def _handle_unix_native_errors(result, cmd, log_permission):
    """Parse Unix zip errors for permission messages and raise if needed."""
    try:
        if result.returncode != 0:
            for line in result.stderr.splitlines():
                if "Permission denied" in line:
                    match = re.search(r"'(.+?)'", line)
                    path = match.group(1) if match else line.split()[-1]
                    log_permission(path)
            # Raise if errors other than permissions occurred
            if result.returncode != 0 and not any("Permission denied" in l for l in result.stderr.splitlines()):
                raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    except KeyboardInterrupt:
        raise


def _zip_with_python(directory_path, zip_path, progress_bar, logger, quiet, log_permission):
    """Fallback zipping using Python zipfile with accurate per-file progress bar."""
    logger.info(f"Zipping using Python zipfile: {zip_path}")

    # Gather all files once
    files = []
    for root, _, filenames in os.walk(directory_path):
        for f in filenames:
            files.append(os.path.join(root, f))

    total_files = len(files)
    if total_files == 0:
        raise ValueError(f"No files found in {directory_path}")

    denied_count = 0

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
        with tqdm(total=total_files, desc="Zipping files", unit="file",
                  disable=not progress_bar, leave=False) as pbar:
            for file_path in files:
                arcname = os.path.relpath(file_path, directory_path)
                try:
                    zipf.write(file_path, str(arcname))
                except PermissionError:
                    denied_count += 1
                    log_permission(file_path)
                except Exception as e:
                    msg = f"Error adding {file_path}: {e}"
                    if logger:
                        logger.error(msg)
                    elif not quiet:
                        print(msg)
                pbar.update(1)  # no manual refresh

    # Log summary of denied files at the end
    if denied_count > 0:
        msg = f"{denied_count} files skipped due to permission errors"
        if logger:
            logger.warning(msg)
        elif not quiet:
            print(msg)
