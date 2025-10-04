import os
import re
from datetime import datetime
from typing import List, Dict, Any


def parse_transfers(log_text: str) -> List[Dict[str, Any]]:
    """
    Parse a log and return a list of transfer dicts with:
    - file = just filename + extension
    - ignores START/END OF LOG lines
    """
    # Block header detection: lines like "===== open | EToGji ====="
    block_start_re = re.compile(r"^===== (\w+)\s*\|\s*(\w+) =====")
    ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    session_colon_re = re.compile(r"\b(\d+):\s")

    # Event-specific patterns
    receiving_re = re.compile(r"(\d+):\s*Receiving\s+'(.+?)'")
    recv_success_re = re.compile(r"(\d+):\s*File received successfully:\s*(.+)")
    recv_error_re = re.compile(r"(\d+):\s*Error receiving file:\s*(.+)")
    sender_failed_re = re.compile(r"Sender failed request validation:\s*(.+)")
    preparing_send_re = re.compile(r"Preparing to send file\s+'(.+?)'")
    sending_re = re.compile(r"Sending\s+'(.+?)'")
    send_success_re = re.compile(r"File sent successfully:\s*(.+)")
    send_denied_re = re.compile(r"Send request denied by receiver|Send request denied")

    # Split into lines, ignoring START/END markers
    lines = [l for l in log_text.splitlines() if "========== START OF LOG ==========" not in l and "========== END OF LOG ==========" not in l]

    blocks = []
    current_block = None
    for line in lines:
        m = block_start_re.match(line)
        if m:
            if current_block:
                blocks.append(current_block)
            current_block = {"type": m.group(1).lower(), "id": m.group(2), "lines": []}
            continue
        if current_block is not None:
            current_block["lines"].append(line)
    if current_block:
        blocks.append(current_block)

    transfers: List[Dict[str, Any]] = []

    for block in blocks:
        btype = block["type"]
        blines = block["lines"]

        if btype == "open":
            sessions: Dict[int, Dict[str, Any]] = {}
            last_session = None

            def make_session(sid: int):
                return {
                    "type": "receive",
                    "session": sid,
                    "file": None,
                    "status": "unknown",
                    "error_message": None,
                    "lines": [],
                    "start_time": None,
                    "end_time": None,
                }

            for line in blines:
                ts_m = ts_re.match(line)
                ts = datetime.strptime(ts_m.group(1), "%Y-%m-%d %H:%M:%S") if ts_m else None

                sess_m = session_colon_re.search(line)
                if sess_m:
                    sid = int(sess_m.group(1))
                    last_session = sid
                    if sid not in sessions:
                        sessions[sid] = make_session(sid)
                    s = sessions[sid]
                    s["lines"].append(line)
                    if ts:
                        s["start_time"] = s["start_time"] or ts
                        s["end_time"] = ts

                    m_recv = receiving_re.search(line)
                    if m_recv:
                        s["file"] = os.path.basename(m_recv.group(2))

                    m_succ = recv_success_re.search(line)
                    if m_succ:
                        s["status"] = "success"
                        s["file"] = os.path.basename(m_succ.group(2))
                    m_err = recv_error_re.search(line)
                    if m_err:
                        s["status"] = "error"
                        s["error_message"] = m_err.group(2)

                else:
                    m_sender_fail = sender_failed_re.search(line)
                    if m_sender_fail:
                        msg = m_sender_fail.group(1)
                        if last_session is not None:
                            s = sessions.setdefault(last_session, make_session(last_session))
                            s["lines"].append(line)
                            s["status"] = "error"
                            s["error_message"] = s.get("error_message") or msg
                            if ts:
                                s["start_time"] = s["start_time"] or ts
                                s["end_time"] = ts
                        else:
                            transfers.append({
                                "type": "receive",
                                "session": None,
                                "file": None,
                                "status": "error",
                                "error_message": msg,
                                "lines": [line],
                                "start_time": ts,
                                "end_time": ts,
                            })
                    else:
                        if last_session is not None:
                            s = sessions.setdefault(last_session, make_session(last_session))
                            s["lines"].append(line)
                            if ts:
                                s["start_time"] = s["start_time"] or ts
                                s["end_time"] = ts

            for sid in sorted(sessions.keys()):
                transfers.append(sessions[sid])

        elif btype == "send":
            transfer = {
                "type": "send",
                "session": block["id"],
                "file": None,
                "status": "unknown",
                "error_message": None,
                "lines": [],
                "start_time": None,
                "end_time": None,
            }

            for line in blines:
                ts_m = ts_re.match(line)
                ts = datetime.strptime(ts_m.group(1), "%Y-%m-%d %H:%M:%S") if ts_m else None
                transfer["lines"].append(line)
                if ts:
                    transfer["start_time"] = transfer["start_time"] or ts
                    transfer["end_time"] = ts

                m_prep = preparing_send_re.search(line)
                if m_prep:
                    transfer["file"] = os.path.basename(m_prep.group(1))
                m_send = sending_re.search(line)
                if m_send and transfer["file"] is None:
                    transfer["file"] = os.path.basename(m_send.group(1))
                m_succ = send_success_re.search(line)
                if m_succ:
                    transfer["status"] = "success"
                    transfer["file"] = transfer["file"] or os.path.basename(m_succ.group(1))
                if send_denied_re.search(line):
                    transfer["status"] = "error"
                    transfer["error_message"] = transfer["error_message"] or "Send request denied by receiver"
                if "ERROR" in line and "Connection attempt" in line:
                    transfer["status"] = "error"
                    transfer["error_message"] = transfer["error_message"] or line.strip()

            transfers.append(transfer)

    return transfers


def sort_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort transfers from newest to oldest by end_time/start_time"""
    def get_dt(t: Dict[str, Any]):
        return t.get("end_time") or t.get("start_time") or datetime.min
    return sorted(entries, key=get_dt)


def print_entries(entries: List[Dict[str, Any]]):
    """
    Print a simple report with duration calculation.
    """
    for i, r in enumerate(entries, 1):
        start = r.get("start_time")
        end = r.get("end_time")
        try:
            duration = str(end - start) if start and end else "N/A"
        except Exception:
            duration = "N/A"

        print(f"=== Report {i} ===")
        print(f"Type    : {r.get('type', 'N/A').capitalize()}")
        print(f"File    : {r.get('file', 'N/A')}")
        print(f"Duration: {duration}")
        print(f"Status  : {r.get('status', 'N/A').capitalize()}")
        print("-" * 50)


def get_history(log_paths: list[str], allow_no_type=False, add_type=True) -> list:
    """
    Parse multiple log files and return a sorted transfer list.
    Filters out entries with invalid statuses unless allow_no_type=True.
    """
    logs = []
    for path in log_paths:
        try:
            with open(path, "r") as f:
                logs.extend(parse_transfers(f.read()))
        except Exception:
            pass

    if add_type:
        for index in range(len(logs)):
            logs[index]["id"] = f"{logs[index]['start_time']}> {logs[index]['type']}, {logs[index]['file']}, {logs[index]['status']}, {logs[index]['session']}"

    # Filter invalid status entries
    valid_statuses = {"success", "error"}
    if not allow_no_type:
        logs = [entry for entry in logs if entry.get("status") in valid_statuses]

    # Sort entries
    sorted_entries = sort_entries(logs)

    return sorted_entries
