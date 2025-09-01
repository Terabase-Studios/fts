import subprocess
import sys
import logging

def cmd_update(args, logger):
    """
    Update FTS via pip.
    Usage: fts update [--verbose]
    """
    logger.error("Update function is not available for this pre-release version\n")
    sys.exit(0)

    logger.info("Updating FTS using pip...")

    # Release
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "fts"]

    try:
        if getattr(args, "verbose", False):
            # Show pip output directly
            subprocess.run(cmd, check=True)
        else:
            # Hide pip output for quiet mode
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("FTS updated successfully!")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to update FTS: {e}")
        logger.info("You can try updating manually with:\n  python -m pip install --upgrade fts")
