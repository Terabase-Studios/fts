#!/usr/bin/env python3
import os
import sys

from fts.core.aliases import resolve_alias, resolve_args
from fts.core.logger import setup_logging
from fts.core.parser import create_parser
from fts.core.secure import is_public_network
from fts import __version__

# --- Lazy command loader with caching ---
_command_cache = {}

def load_cmd(module_path, func_name):
    """Lazy loader for commands, imports on first use and caches the function."""
    def wrapper(args, logger):
        key = (module_path, func_name)
        if key not in _command_cache:
            try:
                mod = __import__(module_path, fromlist=[func_name])
                _command_cache[key] = getattr(mod, func_name)
            except (ImportError, AttributeError) as e:
                logger.error(
                    "Failed to load command. Your install may be corrupted.\n"
                    "Run 'fts update --repair' or reinstall.\n"
                    f"{e}"
                )
                sys.exit(1)
        return _command_cache[key](args, logger)
    return wrapper


def setup_cli_logger(args):
    # --- Setup logger ---
    logfile = getattr(args, "logfile", None)
    log_created = False
    if logfile:
        logfile = resolve_alias(logfile, "dir", logger=None)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(logfile)), exist_ok=True)
            if not os.path.exists(logfile):
                open(logfile, "a").close()
                log_created = True
        except Exception as e:
            print(f"Warning: Could not create logfile '{logfile}': {e}")
            logfile = None

        except Exception as e:
            print(f"Warning: Could not create id: {e}")

    # Determine logging mode based on command
    if "chat" in args.command:
        log_mode = "ptk"  # Use prompt_toolkit mode for chat
    else:
        log_mode = "tqdm"  # Default tqdm-compatible mode

    logger = setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
        logfile=logfile,
        mode=log_mode,
        id=args.command,
    )
    if log_created:
        logger.info(f"Log file created: {logfile}")

    return logger


def ensure_func(args):
    if hasattr(args, "func"):
        return args
    # map command -> (module, func_name)
    mapping = {
        "open": ("fts.commands.server", "cmd_open"),
        "send": ("fts.commands.sender", "cmd_send"),
        "close": ("fts.core.detatched", "cmd_close"),
        "version": ("fts.commands.misc", "cmd_version"),
        "trust": ("fts.core.secure", "cmd_clear_fingerprint"),
        "alias": ("fts.core.aliases", "cmd_alias"),
    }

    if args.command in mapping:
        mod, fn = mapping[args.command]
        args.func = load_cmd(mod, fn)

    return args


# --- Main CLI setup ---
def main():
    if is_public_network("-v" in sys.argv or "--verbose" in sys.argv):
        logger = setup_logging()
        logger.critical('FTS is disabled on public network\n')
        sys.exit(0)
    args = None

    if len(sys.argv) == 1:
        try:
            print(ICON)
            from fts.app.main import start
            start()
            return
        except ImportError:
            print(f"Missing Fts-App!: {e}")
        except Exception as e:
            print(f"Unhandled FTS-App exception!: {e}")

    try:
        parser = create_parser()
        args = parser.parse_args()
    except SystemExit:
        pass

    if not args:
        print('')
        return

    logger = setup_cli_logger(args)
    args = resolve_args(args, logger)
    args = ensure_func(args)

    try:
        args.func(args, logger)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"failed to run command: {e}")
    finally:
        print('')

if __name__ == "__main__":
    main()

XXXX = __version__()
ICON = f"""                                         
         ██████████████████████              
 ██████  ██                    ██     ██████ 
███████████                      ████████████
███████████                       ███████████
  ██████ ██      Terabase's       ██ ██████  
     ██████       FTS-Tool        ██████     
     ██████        v{XXXX}         ██████     
       ████                       ████       
        ████     ▌Graphical      █████       
         ████    Interface▐     ████         
         █████                 █████         
         ███████             ███████         
         ██ ████             ████ ██         
         ██  █████         █████  ██         
         ██   █████       █████   ██         
         ██    █████     █████    ██         
         ██     █████   █████     ██         
         ██      █████ █████      ██         
          ██████████████████████████         
                   ███████                   
                   ███████                   
                    █████         
"""