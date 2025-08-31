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


def cmd_update(args, logger):
    """Update FTS CLI: download latest GitHub release, then upgrade dependencies via pip."""
    logger.info(f"Current FTS version: {VERSION}")

    install_dir = os.path.dirname(os.path.realpath(__file__)).removesuffix("\\src\\fts")

    backup_dir = install_dir + "_backup"

    # --- Step 1: Download latest zip from GitHub ---
    logger.info(f"Fetching latest release from {GITHUB_RELEASE_URL}...")
    try:
        r = requests.get(GITHUB_RELEASE_URL, timeout=15)
        r.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(r.content))
    except Exception as e:
        logger.error(f"Failed to download or read release: {e}")
        sys.exit(1)

    # --- Backup current installation ---
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)
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
        sys.exit(1)

    # --- Step 2: Upgrade dependencies ---
    try:
        # If your repo has requirements.txt
        requirements_path = os.path.join(install_dir, "requirements.txt")
        if os.path.exists(requirements_path):
            logger.info("Installing/updating dependencies from requirements.txt...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", requirements_path, "--upgrade"], check=True)
        else:
            # Otherwise fallback to pip upgrade of package
            logger.info("Upgrading FTS via pip to ensure dependencies...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "fts"], check=True)
        logger.info("Dependencies updated successfully!")
    except subprocess.CalledProcessError as e:
        logger.error(f"Dependency installation failed: {e}")
        logger.warning("FTS updated, but dependencies may be inconsistent.")
        return

    # Cleanup backup if everything succeeded
    shutil.rmtree(backup_dir)
    logger.info("FTS update complete!")


def cmd_version(args, logger):
    print(f"fts version {VERSION}")
