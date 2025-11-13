from fts.app.backend.chat import MUTED_USERS
from fts.app.backend.contacts import replace_with_contact, replace_with_ip, get_seen_users
from fts.app.config import logger


def is_cmd(cmd: str) -> bool:
    for command in COMMAND_KEYS:
        if cmd.startswith(command):
            return True

    return False


def execute(cmd: str) ->  (bool, str):
    if not is_cmd(cmd):
        return False, ""
    else:
        try:
            resonse = _run_cmd(cmd)
            return True, f"--------------------\n{resonse}\n"
        except Exception as e:
            import traceback
            traceback = traceback.format_exc()
            logger.error(f"Failed To run command! {e}\n{traceback}")
            return True, f"--------------------\n{e}\n"

def _run_cmd(cmd: str):
    for command in COMMAND_KEYS:
        if cmd.startswith(command):
            return COMMANDS[command][1](cmd)
    return None


def _get_second_arg(cmd):
    try:
        return cmd.split(" ")[1]
    except IndexError:
        raise Exception("Argument not found")


def _help(cmd: str):
    help_text = [f"{cmd}:\n{info[0]}" for cmd, info in COMMANDS.items()]
    return "\n\n".join(help_text)

def _who(cmd: str):
    ip = _get_second_arg(cmd)
    replaced_ip = replace_with_ip(ip)
    if replaced_ip != ip:
        return f"{ip} -> {replaced_ip}"
    else:
        return f"{replace_with_contact(ip)}, is not a contact"

def _mute(cmd: str):
    ip = _get_second_arg(cmd)
    ip = replace_with_ip(ip)
    users = replace_with_ip(get_seen_users())
    if ip not in users:
        return "IP is not a valid user"

    muted_users = MUTED_USERS.get_muted()
    muted_users.append(ip.strip())
    MUTED_USERS.set_muted(muted_users)
    return f"Muted {replace_with_contact(ip)}"

def _unmute(cmd: str):
    ip = _get_second_arg(cmd)
    ip = replace_with_ip(ip)
    muted = replace_with_ip(MUTED_USERS.get_muted())
    if ip not in muted:
        return "IP is not muted"

    muted_users = MUTED_USERS.get_muted()
    muted_users.pop(muted_users.index(ip.strip()))
    MUTED_USERS.set_muted(muted_users)
    return f"Unmuted {replace_with_contact(ip)}"

def _muted(cmd: str):
    muted = MUTED_USERS.get_muted()
    if muted:
        return "Muted:\n\t" + "\n\t".join(replace_with_contact(muted))
    else:
        return "No users muted."

def _clear(cmd: str):
    return "CLEAR FTS LOG WINDOW"

COMMANDS = {
    "!help":   ("\tUsage: !help\n\tlist commands and what they do", _help),
    "!clear":  ("\tUsage: !clear\n\tclear the chat window", _clear),
    "!who":    ("\tUsage: !who ip\n\tlist the ip of a contact", _who),
    "!muted":  ("\tUsage: !muted\n\tlist muted users", _muted),
    "!mute":   ("\tUsage: !mute ip\n\tblock messages from a user", _mute),
    "!unmute": ("\tUsage: !unmute ip\n\tallow messages from a muted user", _unmute),
}

COMMAND_KEYS = list(COMMANDS.keys())