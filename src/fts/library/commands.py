from fts.config import LIBRARY_FILE
from fts.library.map import LibraryMap
from fts.library.map_manager import browse_map

def cmd_library(args, logger):
    logger.debug(f"Options: {args}")
    if args.task == "manage":
        cmd_manage(args, logger)

def cmd_manage(args, logger):
    try:
        lm = LibraryMap(LIBRARY_FILE)
        browse_map(lm)
    except Exception as e:
        logger.error(f"Library editor failed: {e}")