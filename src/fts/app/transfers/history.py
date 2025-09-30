from datetime import datetime
import re


def parse_transfers(log_text: str):
    transfers = []

    # Patterns
    block_start_re = re.compile(r"===== (\w+) \| (\w+) =====")
    receiving_re = re.compile(r"(\d+): Receiving '(.+)'")
    recv_success_re = re.compile(r"(\d+): File received successfully: (.+)")
    recv_error_re = re.compile(r"(\d+): Error receiving file: (.+)")
    sender_failed_re = re.compile(r"Sender failed request validation: (.+)")
    sending_re = re.compile(r"Sending '(.+)'")
    send_success_re = re.compile(r"File sent successfully: (.+)")
    send_error_re = re.compile(r"ERROR\s+.*Send request denied by receiver")
    timestamp_re = re.compile(r"^(\d{2}:\d{2}:\d{2})")  # capture HH:MM:SS

    current_block_type = None
    current_transfer = None

    for line in log_text.splitlines():
        ts_match = timestamp_re.match(line)
        timestamp = ts_match.group(1) if ts_match else None

        # Detect block start
        block_match = block_start_re.match(line)
        if block_match:
            current_block_type = block_match[1].lower()
            current_transfer = None
            continue

        # ---- RECEIVE BLOCKS ----
        if current_block_type == "open":
            # Start a new receive transfer if "Receiving" line
            m_recv = receiving_re.search(line)
            if m_recv:
                current_transfer = {
                    "type": "receive",
                    "session": int(m_recv.group(1)),
                    "file": m_recv.group(2),
                    "status": "unknown",
                    "lines": [line],
                    "start_time": timestamp,
                    "end_time": timestamp
                }
                continue

            # Start a receive transfer if "Error receiving" line with no active transfer
            m_error = recv_error_re.search(line)
            if m_error:
                if current_transfer is None:
                    current_transfer = {
                        "type": "receive",
                        "session": int(m_error.group(1)),
                        "file": m_error.group(2),
                        "status": "error",
                        "lines": [line],
                        "start_time": timestamp,
                        "end_time": timestamp
                    }
                    transfers.append(current_transfer)
                    current_transfer = None
                    continue
                else:
                    current_transfer["lines"].append(line)
                    current_transfer["status"] = "error"
                    current_transfer["file"] = m_error.group(2)
                    current_transfer["end_time"] = timestamp
                    transfers.append(current_transfer)
                    current_transfer = None
                    continue

            # Include lines like "Sender failed request validation" inside the current transfer
            if sender_failed_re.search(line) and current_transfer:
                current_transfer["lines"].append(line)
                current_transfer["end_time"] = timestamp

            # Add lines to current transfer if active
            if current_transfer and current_transfer["type"] == "receive":
                current_transfer["lines"].append(line)
                current_transfer["end_time"] = timestamp
                # Success detection
                m_success = recv_success_re.search(line)
                if m_success:
                    current_transfer["status"] = "success"
                    current_transfer["file"] = m_success.group(2)
                    transfers.append(current_transfer)
                    current_transfer = None
                continue

        # ---- SEND BLOCKS ----
        elif current_block_type == "send":
            if current_transfer is None:
                # Start a new send transfer
                m_send = sending_re.search(line)
                if m_send:
                    current_transfer = {
                        "type": "send",
                        "session": None,
                        "file": m_send.group(1),
                        "status": "unknown",
                        "lines": [line],
                        "start_time": timestamp,
                        "end_time": timestamp
                    }
                    continue

            if current_transfer and current_transfer["type"] == "send":
                current_transfer["lines"].append(line)
                current_transfer["end_time"] = timestamp
                # Success
                m_success = send_success_re.search(line)
                if m_success:
                    current_transfer["status"] = "success"
                    current_transfer["file"] = m_success.group(1)
                    transfers.append(current_transfer)
                    current_transfer = None
                    continue
                # Error
                m_error = send_error_re.search(line)
                if m_error:
                    current_transfer["status"] = "error"
                    transfers.append(current_transfer)
                    current_transfer = None
                    continue

    # Catch any transfer left unclosed
    if current_transfer:
        transfers.append(current_transfer)

    return transfers


def print_transfer_reports(reports):
    # Determine column widths dynamically for alignment
    type_width = max(len(r.get('type', '')) for r in reports) + 2
    file_width = max(len(str(r.get('file', ''))) for r in reports) + 2
    session_width = max(len(str(r.get('session', ''))) for r in reports) + 2
    time_width = 10  # HH:MM:SS format
    status_width = max(len(r.get('status', '')) for r in reports) + 2
    duration_width = 10

    for i, r in enumerate(reports, 1):
        start = r.get('start_time')
        end = r.get('end_time')
        # Calculate duration if possible
        try:
            duration = str(datetime.strptime(end, "%H:%M:%S") - datetime.strptime(start, "%H:%M:%S"))
        except Exception:
            duration = "N/A"

        print(f"=== Report {i} ===")
        print(f"{'Type':<10}: {r.get('type', 'N/A').capitalize():<{type_width}}")
        print(f"{'File':<10}: {r.get('file', 'N/A'):<{file_width}}")
        print(f"{'Duration':<10}: {duration:<{duration_width}}")
        print(f"{'Status':<10}: {r.get('status', 'N/A').capitalize():<{status_width}}")
        print("-" * 50)

