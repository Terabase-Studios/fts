import logging
import shutil
import textwrap
import sys

from tqdm.asyncio import tqdm_asyncio as tqdm
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI

# ANSI colors
RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
BLUE = "\033[94m"
WHITE = "\033[97m"

LEVEL_COLORS = {
    "DEBUG": "\033[94m",    # light blue
    "INFO": "\033[90m",     # gray
    "WARNING": "\033[33m",  # orange (yellow/orange)
    "ERROR": "\033[91m",    # red
    "CRITICAL": "\033[97;41m"  # white on red
}


class TqdmLoggingHandler(logging.Handler):
    """Logging handler that writes through tqdm to avoid breaking progress bars."""

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, file=sys.stderr)  # keeps bars on stdout, logs on stderr
            sys.stderr.flush()
        except Exception:
            self.handleError(record)

class PTKLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            print_formatted_text(ANSI(msg))
        except Exception:
            self.handleError(record)

class ColorFormatter(logging.Formatter):
    def __init__(self, line_sep=0):
        """
        line_sep: number of blank lines after each log line
        """
        super().__init__("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
        self.line_sep = line_sep

    def format(self, record):
        # Time
        time_str = self.formatTime(record, self.datefmt)
        h, m, s = time_str.split(":")
        colored_time = f"{RED}{h}{WHITE}:{GREEN}{m}{WHITE}:{BLUE}{s}{RESET}"

        # Level
        levelname = record.levelname
        color = LEVEL_COLORS.get(levelname, "")
        padded_level = f"{color}{levelname:<8}{RESET}"

        # Prefix
        prefix = f"{colored_time} | {padded_level} | "
        prefix_len = len(self.strip_ansi(prefix)) + 1

        # Wrap message
        term_width = shutil.get_terminal_size((80, 20)).columns
        wrap_width = max(term_width - prefix_len, 20)
        msg = record.getMessage()
        lines = msg.split("\n") or [""]

        formatted_lines = []
        indent = " " * prefix_len
        for line in lines:
            wrapped = textwrap.wrap(line, width=wrap_width) or [""]
            for i, wline in enumerate(wrapped):
                if formatted_lines:
                    formatted_lines.append(indent + wline)
                else:
                    formatted_lines.append(wline)
            for _ in range(self.line_sep):
                formatted_lines.append("")

        return f"{prefix}{'\n'.join(formatted_lines)}"

    @staticmethod
    def strip_ansi(text):
        import re
        ansi_escape = re.compile(r'\x1b\[([0-9;]*[mK])')
        return ansi_escape.sub('', text)


def setup_logging(verbose=False, quiet=False, logfile=None, line_sep=0, mode="tqdm"):
    """Configure logger for CLI commands with tqdm support."""
    logger = logging.getLogger("fts")
    logger.handlers.clear()

    # Choose stream handler based on mode
    if mode == "ptk":
        stream_handler = PTKLoggingHandler()
    else:
        stream_handler = TqdmLoggingHandler()
    stream_handler.setFormatter(ColorFormatter(line_sep=line_sep))
    logger.addHandler(stream_handler)

    # Level
    if quiet:
        logger.setLevel(logging.ERROR)
    elif verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Optional file logging
    if logfile:
        file_handler = logging.FileHandler(logfile)

        class PlainWrapFormatter(logging.Formatter):
            def __init__(self, line_sep=0):
                super().__init__("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S")
                self.line_sep = line_sep

            def format(self, record):
                prefix = f"{self.formatTime(record, self.datefmt)} | {record.levelname:<8} | "
                prefix_len = len(prefix)
                wrap_width = max(80 - prefix_len, 20)

                msg = record.getMessage()
                lines = msg.split("\n") or [""]

                formatted_lines = []
                indent = " " * prefix_len
                for line in lines:
                    wrapped = textwrap.wrap(line, width=wrap_width) or [""]
                    for i, wline in enumerate(wrapped):
                        if formatted_lines:
                            formatted_lines.append(indent + wline)
                        else:
                            formatted_lines.append(wline)
                    for _ in range(self.line_sep):
                        formatted_lines.append("")

                return f"{prefix}{'\n'.join(formatted_lines)}"

        file_handler.setFormatter(PlainWrapFormatter(line_sep=line_sep))
        logger.addHandler(file_handler)

    return logger
