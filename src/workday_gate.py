#!/usr/bin/env python3
"""Compatibility gate retained for existing LaunchAgents; workers run 24/7."""
import argparse
from datetime import datetime
import json
import subprocess
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Asia/Kolkata")


def local_now():
    return datetime.now(ZONE)


def seconds_remaining(now):
    """Legacy compatibility helper: any aware time is inside the continuous window."""
    if now.utcoffset() is None:
        raise ValueError("An aware clock is required")
    now.astimezone(ZONE)
    return 86400.0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    allowed = seconds_remaining(local_now()) > 0
    if args.check:
        print(json.dumps({"timezone": "Asia/Kolkata", "in_window": allowed, "mode": "continuous_24h"}))
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide a command after --, or use --check")
    if not allowed:
        return 0
    try:
        return subprocess.run(command, shell=False, check=False).returncode
    except OSError:
        print("Continuous worker command could not be started.")
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
