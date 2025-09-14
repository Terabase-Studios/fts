import re
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta
HEADER_RE = re.compile(r"===== ([^|]+) \| ([^\s]+) =====")
LOG_LINE_RE = re.compile(r"(\d{2}:\d{2}:\d{2}) \[\+([^\]]+)\] \| (\w+)\s+\| (.+)")

def clean_log(log_text: str) -> str:
    """
    Cleans a messy logfile (input as text) and returns cleaned log text:
    - Keeps process group headers
    - Removes '| (component|id)' from individual lines
    - Unwraps continuation lines
    - Collapses repeated messages with 'x N'
    - Adds relative time since process start after timestamp
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

        first_time = None
        prev_msg = None
        count = 1

        for line in logs:
            # Extract timestamp
            time_match = time_re.match(line)
            if time_match:
                t_str = time_match.group(1)
                t_obj = datetime.strptime(t_str, "%H:%M:%S")
                if first_time is None:
                    first_time = t_obj
                rel_time = t_obj - first_time
                rel_str = str(rel_time)
                # Format as [+HH:MM:SS]
                rel_str = f"[+{rel_str}]"
                line_clean = line[:8] + " " + rel_str + line[8:]
            else:
                line_clean = line

            if line_clean == prev_msg:
                count += 1
            else:
                if prev_msg and count > 1:
                    output_lines.append(f"{prev_msg} x {count}")
                if line_clean != prev_msg:
                    output_lines.append(line_clean)
                count = 1
                prev_msg = line_clean

        # Flush last repeated message
        if prev_msg and count > 1:
            output_lines.append(f"{prev_msg} x {count}")

        output_lines.append("")  # newline between sections

    output_lines.append("========== END OF LOG ==========")
    return "\n".join(output_lines)


def parse_log(log_text):
    """Parse log into a dictionary of process_id -> list of log entries."""
    sections = defaultdict(list)
    current_process = None
    current_id = None

    for line in log_text.splitlines():
        header_match = HEADER_RE.match(line)
        if header_match:
            current_process, current_id = header_match.groups()
            current_process = current_process.strip()
            continue
        if current_id:
            log_match = LOG_LINE_RE.match(line)
            if log_match:
                time_str, delta, level, message = log_match.groups()
                sections[(current_process, current_id)].append((time_str, delta, level, message))
    return sections


def merge_logs(top_text, bottom_text):
    top_sections = parse_log(top_text)
    bottom_sections = parse_log(bottom_text)

    # Keep top section order, append any new bottom sections
    ordered_keys = list(top_sections.keys())
    for key in bottom_sections.keys():
        if key not in ordered_keys:
            ordered_keys.append(key)

    merged_sections = OrderedDict()

    for key in ordered_keys:
        top_entries = top_sections.get(key, [])
        bottom_entries = bottom_sections.get(key, [])

        all_entries = top_entries + bottom_entries

        # Convert to datetime objects and track day rollover
        dt_entries = []
        prev_time = None
        day_offset = timedelta(0)

        for time_str, _, level, message in all_entries:
            t_obj = datetime.strptime(time_str, "%H:%M:%S")
            if prev_time and t_obj < prev_time:
                day_offset += timedelta(days=1)
            t_obj_with_offset = t_obj + day_offset
            dt_entries.append((t_obj_with_offset, level, message))
            prev_time = t_obj

        # Sort entries chronologically
        dt_entries.sort(key=lambda x: x[0])

        # Recalculate relative delta
        first_time = dt_entries[0][0] if dt_entries else None
        recalculated = []
        for t_obj, level, message in dt_entries:
            delta = t_obj - first_time
            recalculated.append((t_obj.time().strftime("%H:%M:%S"), str(delta), level, message))

        merged_sections[key] = recalculated

    # Reconstruct log text
    merged_text = ["========== START OF LOG ==========\n"]
    for (proc, pid), entries in merged_sections.items():
        merged_text.append(f"===== {proc} | {pid} =====")
        for time_str, delta, level, message in entries:
            merged_text.append(f"{time_str} [+{delta}] | {level:<8} | {message}")
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
    if not save_path:
        save_path = log_path

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