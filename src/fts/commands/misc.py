import fts

def cmd_version(args, logger):
    logger.info(f"fts version {fts.__version__()}")
