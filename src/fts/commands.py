import sys
import os
import subprocess
import requests
import zipfile
import io
import shutil
from .config import (
    VERSION,
    GITHUB_RELEASE_URL,
)


import os
import sys
import io
import shutil
import zipfile
import subprocess
import requests
from .config import VERSION

GITHUB_API_LATEST = "https://api.github.com/repos/Terabase-Studios/fts/releases/latest"

def cmd_update(args, logger):
    """Update FTS CLI: download latest GitHub release, then upgrade dependencies via pip."""
    logger.info(f"Current FTS version: {VERSION}")

    # Determine install directory
    install_dir = os.path.dirname(os.path.realpath(__file__))
    backup_dir = install_dir + "_backup"

    # --- Step 1: Get latest release zip URL from GitHub API ---
    logger.info("Fetching latest release info from GitHub...")
    try:
        r = requests.get(GITHUB_API_LATEST, timeout=15)
        r.raise_for_status()
        release = r.json()
        zip_url = None
        for asset in release.get("assets", []):
            if asset["name"].endswith(".zip"):
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

    # --- Download the zip ---
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
        shutil.rmtree(backup_dir)
    if os.path.exists(install_dir):
        os.rename(install_dir, backup_dir)

    # --- Extract new release ---
    try:
        zf.extractall(install_dir)
        logger.info("FTS updated from GitHub successfully!")
    except Exception as e:
        logger.error(f"Failed to extract update: {e}")
        # Rollback
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir)
        os.rename(backup_dir, install_dir)
        logger.info("Rollback completed.")
        return

    # --- Step 2: Upgrade dependencies ---
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
        return

    # Cleanup backup if everything succeeded
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)
    logger.info("FTS update complete!")


def cmd_version(args, logger):
    print(f"fts version {VERSION}")
