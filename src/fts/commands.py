import sys
import os
import subprocess
import requests
import zipfile
import io
import shutil
from .config import (
    VERSION,
    GITHUB_API_LATEST,
)

MAX_RETRIES = 5
RETRY_DELAY = 1  # seconds

def safe_remove(path, logger):
    """Remove a file or directory safely, with retries on Windows."""
    for attempt in range(MAX_RETRIES):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.isfile(path):
                os.remove(path)
            return True
        except PermissionError as e:
            logger.warning(f"PermissionError removing {path}, attempt {attempt+1}: {e}")
            time.sleep(RETRY_DELAY)
    logger.error(f"Failed to remove {path} after {MAX_RETRIES} attempts")
    return False

def safe_rename(src, dst, logger):
    """Rename a file or directory safely, with fallback if Windows blocks it."""
    for attempt in range(MAX_RETRIES):
        try:
            os.rename(src, dst)
            return True
        except PermissionError as e:
            logger.warning(f"PermissionError renaming {src} -> {dst}, attempt {attempt+1}: {e}")
            time.sleep(RETRY_DELAY)
    # Fallback: copy + remove
    try:
        shutil.copytree(src, dst)
        safe_remove(src, logger)
        return True
    except Exception as e:
        logger.error(f"Failed fallback copy/move for {src} -> {dst}: {e}")
        return False

def cmd_update(args, logger):
    """Update FTS CLI: download latest release, backup, extract, and upgrade dependencies."""
    logger.info(f"Current FTS version: {VERSION}")

    install_dir = os.path.dirname(os.path.realpath(__file__)).removesuffix("\\src\\fts")
    backup_dir = install_dir + "_backup"

    # --- Fetch latest release ---
    logger.info("Fetching latest release info from GitHub...")
    try:
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
        logger.error(f"Failed to fetch latest release info: {e}")
        return

    # --- Download zip ---
    logger.info(f"Downloading latest release from {zip_url}...")
    try:
        r = requests.get(zip_url, timeout=30)
        r.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        bad_file = zf.testzip()
        if bad_file:
            logger.error(f"Downloaded zip is corrupted, bad file: {bad_file}")
            return
    except Exception as e:
        logger.error(f"Failed to download or read zip: {e}")
        return

    # --- Backup current installation ---
    if os.path.exists(backup_dir):
        safe_remove(backup_dir, logger)
    if os.path.exists(install_dir):
        if not safe_rename(install_dir, backup_dir, logger):
            logger.error("Cannot backup current installation. Aborting update.")
            return

    # --- Extract new release ---
    try:
        os.makedirs(install_dir, exist_ok=True)
        zf.extractall(install_dir)
        logger.info("FTS updated from GitHub successfully!")
    except Exception as e:
        logger.error(f"Failed to extract update: {e}")
        # Rollback
        safe_remove(install_dir, logger)
        if os.path.exists(backup_dir):
            safe_rename(backup_dir, install_dir, logger)
        logger.info("Rollback completed.")
        return

    # --- Upgrade dependencies ---
    try:
        requirements_path = os.path.join(install_dir, "requirements.txt")
        if os.path.exists(requirements_path):
            logger.info("Installing/updating dependencies from requirements.txt...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", requirements_path, "--upgrade"], check=True)
        else:
            logger.info("Upgrading FTS via pip to ensure dependencies...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "fts"], check=True)
        logger.info("Dependencies updated successfully!")
    except subprocess.CalledProcessError as e:
        logger.error(f"Dependency installation failed: {e}")
        logger.warning("FTS updated, but dependencies may be inconsistent.")

    # --- Cleanup backup ---
    if os.path.exists(backup_dir):
        safe_remove(backup_dir, logger)
    logger.info("FTS update complete!")



def cmd_version(args, logger):
    print(f"fts version {VERSION}")
