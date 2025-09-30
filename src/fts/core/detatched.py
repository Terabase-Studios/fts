import argparse
import os
import shutil
import subprocess
import sys

import psutil

from fts.cli import create_parser
from fts.config import RECEIVING_PID


def cmd_close(args, logger):
    logger.debug("Closing detached FTS server(s)")
    logger.debug(f"Options: {vars(args)}")

    end_detached(args, logger, RECEIVING_PID, "receiving")


def start_detached(args, logger, pid_file, server_name) -> bool:
    """
    Start in detached mode (completely detached: no console, no I/O).
    Returns True if parent should exit, False otherwise.
    """
    if not getattr(args, "detached", False):
        return False

    logger.debug(f"Options: {args}")

    # Check for existing PID
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                old_pid = int(f.read().strip())
            if psutil.pid_exists(old_pid):
                p = psutil.Process(old_pid)
                logger.info(f"{server_name} server already running (PID {old_pid})")
                logger.info(f"Run 'fts close {server_name}' to end current {server_name} server")
                logger.debug(f"cmd: {' '.join(p.cmdline())}")
                return True
            else:
                logger.warning("Stale PID file found, removing")
                os.remove(pid_file)
        except Exception as e:
            logger.warning(f"Failed to read PID file: {e}")
            os.remove(pid_file)

    # Copy args but remove -d/--detached
    parser = create_parser()
    arguments = namespace_to_argv(parser, args)
    for flag in ("-d", "--detached"):
        if flag in arguments:
            arguments.remove(flag)

    # Prefer installed CLI script, fallback to -m
    fts_executable = shutil.which("fts")
    if fts_executable:
        cmd = [fts_executable] + arguments
    else:
        cmd = [sys.executable, "-m", "fts"] + arguments

    # Prepare kwargs for Popen
    startupinfo = subprocess.STARTUPINFO() if os.name == "nt" else False
    if startupinfo:
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    kwargs = dict(
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )

    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        kwargs["startupinfo"] = startupinfo
    else:
        kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **kwargs, shell=False)
        # Write PID to file
        with open(pid_file, "w") as f:
            f.write(str(proc.pid))
        logger.info(f" {server_name} server started in detached mode (PID {proc.pid})")
    except Exception as e:
        logger.error(f"Error launching {server_name} server: {e}")
        return True

    # Parent should exit
    return True

def end_detached(args, logger, pid_file, server_name):
    """
    Stops the detached FTS server if it's running.
    """

    logger.debug(f"Preparing to close {server_name} server")
    logger.debug(f"Options: {vars(args)}")

    if not os.path.exists(pid_file):
        logger.warning(f"No PID file found, {server_name} server may not be running.")
        return

    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
    except Exception as e:
        logger.error(f"Failed to read PID file: {e}")
        return

    if not psutil.pid_exists(pid):
        logger.warning(f"No process with PID {pid} found. Removing stale PID file.")
        os.remove(pid_file)
        return

    try:
        proc = psutil.Process(pid)
        logger.info(f"Stopping {server_name} server (PID {pid})")
        logger.debug(f"cmd: {' '.join(proc.cmdline())}")
        proc.terminate()  # send SIGTERM on Unix / terminate on Windows
        try:
            proc.wait(timeout=5)  # wait up to 5 seconds
            logger.info("Server stopped successfully.")
        except psutil.TimeoutExpired:
            logger.warning("Server did not stop in time. Killing forcibly.")
            proc.kill()
        os.remove(pid_file)
    except Exception as e:
        logger.error(f"Failed to stop server PID {pid}: {e}")

def namespace_to_argv(parser: argparse.ArgumentParser, namespace: argparse.Namespace):
    argv = []
    ns_dict = vars(namespace)

    subparser_action = None
    subparser_name = None

    # Phase 1: parent args (except subparser)
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparser_action = action
            subparser_name = ns_dict.get(action.dest)
            continue

        value = ns_dict.get(action.dest, None)

        if not action.option_strings:
            # positional
            if value is not None:
                if isinstance(value, list):
                    argv.extend(map(str, value))
                else:
                    argv.append(str(value))
        else:
            # option
            if isinstance(action, argparse._StoreTrueAction):
                if value:
                    argv.append(action.option_strings[-1])
            elif isinstance(action, argparse._StoreFalseAction):
                if not value:
                    argv.append(action.option_strings[-1])
            elif isinstance(value, list):
                for v in value:
                    argv.extend([action.option_strings[-1], str(v)])
            elif value is not None:
                argv.extend([action.option_strings[-1], str(value)])
            # else: skip if value is None

    # Phase 2: subparser
    if subparser_action and subparser_name:
        argv.append(subparser_name)
        subparser = subparser_action.choices[subparser_name]
        # Phase 3: recurse into chosen subparser
        argv.extend(namespace_to_argv(subparser, namespace))

    return argv