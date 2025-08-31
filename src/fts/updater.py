import sys
import os
import subprocess
import requests
import zipfile
import io
import time
import shutil
import tempfile
from tqdm import tqdm

GITHUB_API_LATEST = "https://api.github.com/repos/Terabase-Studios/fts/releases/latest"
MAX_RETRIES = 5
RETRY_DELAY = 1  # seconds

def safe_copy(src, dst, logger):
    """Copy a file or folder safely, retrying on Windows locks. Skip .git folders."""
    if ".git" in src.split(os.sep):
        logger.debug(f"Skipping .git folder/file: {src}")
        return True
    for attempt in range(MAX_RETRIES):
        try:
            if os.path.isdir(src):
                if not os.path.exists(dst):
                    os.makedirs(dst)
                for item in os.listdir(src):
                    s_item = os.path.join(src, item)
                    d_item = os.path.join(dst, item)
                    safe_copy(s_item, d_item, logger)
            else:
                shutil.copy2(src, dst)
            return True
        except PermissionError as e:
            logger.warning(f"PermissionError copying {src} -> {dst}, attempt {attempt+1}: {e}")
            time.sleep(RETRY_DELAY)
    logger.error(f"Failed to copy {src} -> {dst} after {MAX_RETRIES} attempts")
    return False

def safe_remove(path, logger):
    """Remove files or folders, skipping locked files like .git."""
    for attempt in range(MAX_RETRIES):
        try:
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for d in list(dirs):
                        if d == ".git":
                            dirs.remove(d)  # skip .git
                    for f in files:
                        try:
                            os.remove(os.path.join(root, f))
                        except PermissionError:
                            logger.warning(f"Skipping locked file {f}")
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.isfile(path):
                os.remove(path)
            return True
        except PermissionError as e:
            logger.warning(f"PermissionError removing {path}, attempt {attempt+1}: {e}")
            time.sleep(RETRY_DELAY)
    logger.error(f"Failed to remove {path} after {MAX_RETRIES} attempts")
    return False

def cmd_update(args, logger):
    """Windows-safe updater using temporary folder and file-by-file replacement."""
    logger.debug(f"Preparing to update")
    logger.debug(f"Options: {vars(args)}\n")

    install_dir = os.path.dirname(os.path.realpath(__file__)).removesuffix("\\src\\fts")
    backup_dir = install_dir + "_backup"

    # --- Fetch latest release ---
    try:
        logger.info("Fetching latest release info from GitHub...")
        r = requests.get(GITHUB_API_LATEST, timeout=15)
        r.raise_for_status()
        release = r.json()
        zip_url = None
        for asset in release.get("assets", []):
            if asset["name"].lower().endswith(".zip"):
                zip_url = asset["browser_download_url"]
                break
        if not zip_url:
            zip_url = release.get("zipball_url", None)
            if not zip_url:
                logger.error("No zip asset found in latest release!")
                return
    except Exception as e:
        logger.error(f"Failed to fetch release info: {e}")
        return

    # --- Download with progress bar ---
    try:
        logger.info(f"Downloading latest release from {zip_url}...")
        with requests.get(zip_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            chunks = []
            with tqdm(total=total, unit='B', unit_scale=True, desc="Downloading", disable=not args.progress) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        chunks.append(chunk)
                        pbar.update(len(chunk))
            r_content = b"".join(chunks)
            zf = zipfile.ZipFile(io.BytesIO(r_content))
            bad_file = zf.testzip()
            if bad_file:
                logger.error(f"Downloaded zip is corrupted, bad file: {bad_file}")
                return
    except Exception as e:
        logger.error(f"Failed to download or read zip: {e}")
        return

    # --- Extract to temporary folder ---
    tmp_dir = tempfile.mkdtemp(prefix="fts_update_")
    try:
        zf.extractall(tmp_dir)
        logger.debug(f"Extracted update to temporary folder {tmp_dir}")
    except Exception as e:
        logger.error(f"Failed to extract update: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    # --- Backup current installation ---
    if os.path.exists(backup_dir):
        safe_remove(backup_dir, logger)
    if os.path.exists(install_dir):
        if not safe_copy(install_dir, backup_dir, logger):
            logger.error("Cannot backup current installation. Update aborted.")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return
        logger.debug(f"Backup of current installation created at {backup_dir}")

    # --- Replace files individually with progress ---
    try:
        top_level = next(os.scandir(tmp_dir)).path
        items = os.listdir(top_level)
        for item in tqdm(items, desc="Updating files", disable=not args.progress):
            src_item = os.path.join(top_level, item)
            dst_item = os.path.join(install_dir, item)
            safe_copy(src_item, dst_item, logger)
        logger.debug("Files replaced successfully.")
    except Exception as e:
        logger.error(f"Failed during file replacement: {e}")
        logger.info("Attempting rollback...")
        if os.path.exists(backup_dir):
            safe_copy(backup_dir, install_dir, logger)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # --- Upgrade dependencies ---
    try:
        requirements_path = os.path.join(install_dir, "requirements.txt")
        if os.path.exists(requirements_path):
            logger.info("Installing/updating dependencies...")
            cmd = [sys.executable, "-m", "pip", "install", "-r", requirements_path, "--upgrade"]
        else:
            logger.info("Upgrading FTS via pip...")
            cmd = [sys.executable, "-m", "pip", "install", "-e", install_dir]

        if args.verbose:
            subprocess.run(cmd, check=True)  # prints output directly
        else:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logger.debug("Dependencies updated successfully!")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Dependency installation may be inconsistent: {e}")

    # --- Cleanup backup if everything succeeded ---
    if os.path.exists(backup_dir):
        safe_remove(backup_dir, logger)
    logger.info("FTS update complete!")
