#!/usr/bin/env python3
"""Run a command only during 08:00–20:00 Asia/Kolkata, every day."""
import argparse
from datetime import datetime
import json
import subprocess
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Asia/Kolkata")


def local_now():
    return datetime.now(ZONE)


def seconds_remaining(now):
    if now.utcoffset() is None:
        raise ValueError("An aware clock is required")
    local = now.astimezone(ZONE)
    if not 8 <= local.hour < 20:
        return 0
    return (local.replace(hour=20, minute=0, second=0, microsecond=0) - local).total_seconds()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    allowed = seconds_remaining(local_now()) > 0
    if args.check:
        print(json.dumps({"timezone": "Asia/Kolkata", "in_window": allowed}))
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide a command after --, or use --check")
    if not allowed:
        return 0
    try:
        return subprocess.run(command, shell=False, check=False).returncode
    except OSError:
        print("Workday command could not be started.")
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
