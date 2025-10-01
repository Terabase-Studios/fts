import re
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta

HEADER_RE = re.compile(r"===== ([^|]+) \| ([^\s]+) =====")
LOG_LINE_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+)\s*\| (.+)")

# Shared time parsing helper
def parse_time_with_rollover(entries):
    """
    Given a list of (time_str, level, message),
    detect midnight rollover and return [(datetime, level, message)].
    """
    dt_entries = []
    prev_time = None
    day_offset = timedelta(0)

    for time_str, level, message in entries:
        t_obj = datetime.strptime(time_str, "%H:%M:%S")
        if prev_time and t_obj < prev_time:
            # rolled over past midnight
            day_offset += timedelta(days=1)
        t_obj_with_offset = t_obj + day_offset
        dt_entries.append((t_obj_with_offset, level, message))
        prev_time = t_obj
    return dt_entries


def clean_log(log_text: str) -> str:
    """
    Cleans a messy logfile (input as text) and returns cleaned log text:
    - Keeps process group headers
    - Removes '| (component|id)' from individual lines
    - Unwraps continuation lines
    - Collapses repeated messages with 'x N'
    - Adds relative time since process start after timestamp
    - Handles midnight rollovers properly
    """
    tag_re = re.compile(r"\(([^|]+)\|([^)]+)\)")
    full_tag_re = re.compile(r"\| \([^)]+\) ")
    time_re = re.compile(r"^(\d{2}:\d{2}:\d{2}) \|")

    grouped_logs = {}
    group_order = []
    buffer = ""
    current_tag = None

    for line in log_text.splitlines():
        raw = line.rstrip("\n")
        if raw.strip() == "":
            if buffer and current_tag:
                grouped_logs[current_tag].append(buffer)
                buffer = ""
            continue

        match = tag_re.search(raw)
        if match:
            if buffer and current_tag:
                grouped_logs[current_tag].append(buffer)
            current_tag = (match.group(1), match.group(2))
            if current_tag not in grouped_logs:
                grouped_logs[current_tag] = []
                group_order.append(current_tag)
            buffer = full_tag_re.sub("", raw)
        else:
            buffer += " " + raw.strip()
    if buffer and current_tag:
        grouped_logs[current_tag].append(buffer)

    # Build cleaned log text
    output_lines = ["========== START OF LOG ==========\n"]
    for component, proc_id in group_order:
        output_lines.append(f"===== {component} | {proc_id} =====")
        logs = grouped_logs[(component, proc_id)]

        parsed_entries = []
        for line in logs:
            time_match = time_re.match(line)
            if time_match:
                t_str = time_match.group(1)
                parsed_entries.append((t_str, "LINE", line))  # keep raw line with tag
            else:
                parsed_entries.append((None, "CONT", line))

        # Handle day rollover
        dt_entries = []
        prev_time = None
        day_offset = timedelta(0)
        for t_str, kind, line in parsed_entries:
            if t_str:
                t_obj = datetime.strptime(t_str, "%H:%M:%S")
                if prev_time and t_obj < prev_time:
                    day_offset += timedelta(days=1)
                prev_time = t_obj
                dt_entries.append((t_obj + day_offset, kind, line))
            else:
                dt_entries.append((None, kind, line))

        # Sort and format
        first_time = min([t for t, k, _ in dt_entries if t is not None], default=None)
        prev_msg = None
        count = 1
        for t_obj, kind, line in dt_entries:
            if kind == "LINE":
                rel_time = t_obj - first_time if first_time else timedelta(0)
                rel_str = f"[+{rel_time}]"
                line_clean = line[:8] + " " + rel_str + line[8:]
            else:
                line_clean = line

            if line_clean == prev_msg:
                count += 1
            else:
                if prev_msg and count > 1:
                    output_lines.append(f"{prev_msg} x {count}")
                output_lines.append(line_clean)
                count = 1
                prev_msg = line_clean

        if prev_msg and count > 1:
            output_lines.append(f"{prev_msg} x {count}")

        output_lines.append("")  # newline between sections

    output_lines.append("========== END OF LOG ==========")
    return "\n".join(output_lines)


def parse_log(text):
    sections = defaultdict(list)
    current_section = None

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("=========="):
            continue

        m = HEADER_RE.match(line)
        if m:
            proc, pid = m.groups()
            current_section = (proc, pid)
            continue

        m = LOG_LINE_RE.match(line)
        if m and current_section:
            dt_str, level, message = m.groups()
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            sections[current_section].append((dt, level, message))

    return sections


def merge_logs(top_text, bottom_text):
    top_sections = parse_log(top_text)
    bottom_sections = parse_log(bottom_text)

    # union of all keys
    ordered_keys = list(top_sections.keys())
    for key in bottom_sections.keys():
        if key not in ordered_keys:
            ordered_keys.append(key)

    merged_sections = OrderedDict()
    for key in ordered_keys:
        all_entries = top_sections.get(key, []) + bottom_sections.get(key, [])
        # Sort chronologically by datetime
        all_entries.sort(key=lambda x: x[0])
        merged_sections[key] = all_entries

    # Reconstruct log text
    merged_text = ["========== START OF LOG ==========\n"]
    for (proc, pid), entries in merged_sections.items():
        merged_text.append(f"===== {proc} | {pid} =====")
        for dt_obj, level, message in entries:
            merged_text.append(f"{dt_obj.strftime('%Y-%m-%d %H:%M:%S')} | {level:<8} | {message}")
        merged_text.append("")
    merged_text.append("========== END OF LOG ==========\n")
    return "\n".join(merged_text)




def split_logs(log_text: str):
    """
    Splits a log text into the sorted portion (up to END OF LOG) and
    the remaining unsorted portion (after END OF LOG).

    Returns:
        sorted_log_text (str | None): everything up to and including END OF LOG, or None if not found
        bottom_unsorted_log (str): everything after END OF LOG, or the whole log if no END OF LOG
    """
    end_marker = "========== END OF LOG =========="
    parts = log_text.split(end_marker, 1)  # split at first occurrence

    if len(parts) == 2:
        sorted_log = parts[0].rstrip() + "\n" + end_marker  # include marker
        bottom_unsorted = parts[1].lstrip()  # remove leading whitespace/newlines
        return sorted_log, bottom_unsorted if bottom_unsorted else ""
    else:
        # END OF LOG not found → nothing is sorted
        return None, log_text


def organize_log(log_path: str, save_path: str = None):
    with open(log_path, "r", encoding="utf-8") as f:
        log_text = f.read()

    if log_text == "":
        return

    top, bottom = split_logs(log_text)

    if top is None:
        top = clean_log(bottom)
        bottom = None

    new_log = top

    if bottom is not None:
        bottom = clean_log(bottom)
        new_log = merge_logs(top, bottom)

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(new_log)