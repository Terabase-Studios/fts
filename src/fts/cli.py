#!/usr/bin/env python3
import os
import sys
import traceback

from fts import __version__
from fts.core.aliases import resolve_alias, resolve_args
from fts.core.logger import setup_logging
from fts.core.parser import create_parser
from fts.core.secure import is_public_network

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
                import traceback
                tb = e.__traceback__
                traceback_str = ''.join(traceback.format_tb(tb))
                logger.error(
                    "Failed to load command. Your install may be corrupted.\n"
                    f"{traceback_str}",
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
        "cache": ("fts.commands.cache", "cmd_cache"),
        "plugins": ("fts.app.backend.plugins.commands", "cmd_plugins"),
    }

    if args.command in mapping:
        mod, fn = mapping[args.command]
        args.func = load_cmd(mod, fn)

    return args


# --- Main CLI setup ---
def main():
    if "--version" in sys.argv:
        print(__version__(), '\n')
        sys.exit(0)

    if "--app-logo" in sys.argv:
        print(ICON)
        sys.exit(0)

    if is_public_network("-v" in sys.argv or "--verbose" in sys.argv):
        logger = setup_logging()
        logger.critical('FTS is disabled on public network\n')
        sys.exit(1)
    args = None

    if len(sys.argv) == 1:
        try:
            print(ICON)
            from fts.app.main import start
            start()
            return
        except ImportError as e:
            print(f"Missing Fts-App!: {e}")
        except Exception as e:
            print(f"Unhandled FTS-App exception!:\n{traceback.format_exc()}")

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

def colorize_icon(icon: str, version: str) -> str:
    RESET = "\033[0m"

    NAME   = "\033[38;2;205;205;205m"
    VERSION = RESET
    LABEL = "\033[38;2;150;150;150m"

    # Define your three RGB constants for the gradient
    COLOR1 = (255, 0, 0)    # top-left (red)
    COLOR2 = (127, 0, 227)    # middle (green)
    COLOR3 = (0, 0, 255)    # bottom-right (blue)

    lines = icon.splitlines()
    height = len(lines)
    width = max(len(line) for line in lines) if lines else 1

    def rgb(r, g, b):
        return f"\033[38;2;{r};{g};{b}m"

    out = []

    for y, line in enumerate(lines):
        new_line = []
        for x, ch in enumerate(line):
            if ch == "█":
                # Normalize position along diagonal
                t = (x + y) / (width + height - 2)  # 0 → 1

                # Interpolate three colors
                if t < 0.5:
                    ratio = t / 0.5
                    r = int(COLOR1[0] * (1 - ratio) + COLOR2[0] * ratio)
                    g = int(COLOR1[1] * (1 - ratio) + COLOR2[1] * ratio)
                    b = int(COLOR1[2] * (1 - ratio) + COLOR2[2] * ratio)
                else:
                    ratio = (t - 0.5) / 0.5
                    r = int(COLOR2[0] * (1 - ratio) + COLOR3[0] * ratio)
                    g = int(COLOR2[1] * (1 - ratio) + COLOR3[1] * ratio)
                    b = int(COLOR2[2] * (1 - ratio) + COLOR3[2] * ratio)

                new_line.append(rgb(r, g, b) + ch + RESET)
            else:
                new_line.append(ch)

        colored = "".join(new_line)

        # Text accents (overlay after gradient)
        if "Terabase's" in colored:
            colored = colored.replace("Terabase's", f"{NAME}Terabase's{RESET}")
        if "FTS-Tool" in colored:
            colored = colored.replace("FTS-Tool", f"{NAME}FTS-Tool{RESET}")
        if f"v{version}" in colored:
            colored = colored.replace(f"v{version}", f"{VERSION}v{version}{RESET}")
        if "▌Graphical" in colored or "Interface▐" in colored:
            colored = colored.replace("▌Graphical", f"{LABEL}▌Graphical{RESET}")
            colored = colored.replace("Interface▐", f"{LABEL}Interface▐{RESET}")

        out.append(colored)

    return "\n".join(out)


XXXX = __version__()
ICON = colorize_icon(f"""                                         
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
""", XXXX)