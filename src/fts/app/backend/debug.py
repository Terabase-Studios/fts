import re
from datetime import datetime
from typing import List, Optional

from rich.text import Text

from fts.app.cache import DEBUG_FILE

HEADER_RE = re.compile(r"^===== APP \| ([A-Za-z0-9]+) =====$")
TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
LINE_RE = re.compile(
    r"""
    ^
    (?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})
    \s*\|\s*
    (?P<level>[^|]+?)          # anything up to next |
    \s*\|\s*
    (?P<rest>.*)
    $
    """,
    re.VERBOSE
)
BRACKET_RE = re.compile(r"\[([^\]]+)\]")
LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \|\s+"
    r"(?P<level>\w+)\s+\|\s+"
    r"(?P<context>(?:\[[^\]]+\])+)\s*"
    r"(?P<message>.*)$"
)
LEVEL_STYLES = {
    "DEBUG": "dim cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold white on red",
}


def parse_log() -> tuple:
    with open(DEBUG_FILE, "r") as log_file:
        parsed_log = parse_log_instances(log_file)
        for instance in parsed_log:
            instance_data = parsed_log[instance]
            log_lines = instance_data[2]
            parsed_lines = []
            for log_line in log_lines:
                parsed = parse_log_line(log_line)
                if parsed:
                    parsed_lines.append(parsed)
            instance_data[2] = parsed_lines
            parsed_log[instance] = instance_data
        return parsed_log, generate_metadata(parsed_log)


def parse_log_instances(file):
    sessions = {}

    current_id = None
    current_lines = []
    start_time = None
    end_time = None

    def finalize():
        if current_id is not None:
            sessions[current_id] = [
                start_time,
                end_time,
                current_lines.copy()
            ]

    with file as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")

            header_match = HEADER_RE.match(line)
            if header_match:
                # Finish previous block
                finalize()

                # Start new block
                current_id = header_match.group(1)
                current_lines = []
                start_time = None
                end_time = None
                continue

            if current_id is None:
                # Ignore anything before first header
                continue

            current_lines.append(line)

            ts_match = TIMESTAMP_RE.match(line)
            if ts_match:
                ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                if start_time is None:
                    start_time = ts
                end_time = ts

        # finalize last block
        finalize()

    return sessions


def parse_log_line(line):
    line = line.strip()
    match = LINE_RE.match(line)
    if not match:
        return None

    timestamp = datetime.strptime(match.group("time"), "%Y-%m-%d %H:%M:%S")
    level = match.group("level").strip()
    remainder = match.group("rest")

    brackets = BRACKET_RE.findall(remainder)

    module = brackets[0] if len(brackets) >= 1 else None
    submodule = brackets[1] if len(brackets) >= 2 else None

    return {
        "time": timestamp,
        "level": level,
        "module": module,
        "submodule": submodule,
        "line": line,
    }


def generate_metadata(data: dict):
    selection_tree = {}
    for instance in data:
        instance_branch = {"severity": set(), "modules": {}}
        for line in data[instance][2]:
            if not line:
                continue
            instance_branch["severity"].add(line['level'])
            if not instance_branch["modules"].get(line['module']):
                instance_branch["modules"][line['module']] = set()
            if line.get("submodule"):
                instance_branch["modules"][line['module']].add(line["submodule"])
        for module in instance_branch["modules"]:
            if not instance_branch["modules"][module]:
                instance_branch["modules"][module] = None
        selection_tree[instance] = instance_branch
    return selection_tree


def colorize_log_line(line: str) -> Text:
    pattern = (
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \|\s+"
        r"(?P<level>\w+)\s+\|\s+"
        r"(?P<context>(?:\[[^\]]+\])+)\s*"
        r"(?P<message>.*)$"
    )

    match = re.match(pattern, line)
    if not match:
        return Text(line, style="dim")

    parts = match.groupdict()
    text = Text()

    # Timestamp
    text.append(parts["timestamp"], style="dim")
    text.append(" | ")

    # Level
    level = parts["level"]
    text.append(f"{level:<8}", style=LEVEL_STYLES.get(level, "white"))
    text.append(" | ")

    # Context blocks (handles 1 or many)
    contexts = re.findall(r"\[([^\]]+)\]", parts["context"])
    for i, ctx in enumerate(contexts):
        text.append("[", style="dim")
        style = "bold magenta" if i == 0 else "cyan"
        text.append(ctx, style=style)
        text.append("]", style="dim")

    if parts["message"]:
        text.append(" ")
        text.append(parts["message"])

    return text


def parse_log_line(line: str):
    match = LOG_PATTERN.match(line)
    if not match:
        return None

    parts = match.groupdict()
    contexts = re.findall(r"\[([^\]]+)\]", parts["context"])

    module = contexts[0] if len(contexts) >= 1 else None
    submodule = contexts[1] if len(contexts) >= 2 else None

    return {
        "timestamp": parts["timestamp"],
        "level": parts["level"],
        "module": module,
        "submodule": submodule,
        "message": parts["message"],
        "raw": line,
    }


def filter_logs(
        lines: List[str],
        level: Optional[str] = None,
        module: Optional[str] = None,
        submodule: Optional[str] = None,
) -> List[str]:
    results = []

    for line in lines:
        line = str(line)
        parsed = parse_log_line(line)
        if not parsed:
            continue

        if level and parsed["level"] != level:
            continue

        if module and parsed["module"] != module:
            continue

        if submodule and parsed["submodule"] != submodule:
            continue

        results.append(parsed["raw"])

    return results
