#!/usr/bin/env python3
"""On AC power, prevent idle system sleep until 20:00; allow display/manual sleep."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from workday_gate import local_now, seconds_remaining


def power_source():
    try:
        result = subprocess.run(["/usr/bin/pmset", "-g", "batt"], capture_output=True,
                                text=True, timeout=2, check=False)
        if result.returncode != 0:
            return "UNKNOWN"
        first = result.stdout.splitlines()[0].strip()
        return {"Now drawing from 'AC Power'": "AC",
                "Now drawing from 'Battery Power'": "BATTERY"}.get(first, "UNKNOWN")
    except Exception:
        return "UNKNOWN"


@contextmanager
def instance_lock(path):
    path = Path(path).expanduser()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(descriptor)  # Releases the advisory lock; never stores a PID.


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2)
    else:
        child.wait(timeout=2)


def hold_awake(clock=None, power=None, sleep=None, popen=None):
    clock, power = clock or local_now, power or power_source
    sleep, popen = sleep or time.sleep, popen or subprocess.Popen
    child = None
    try:
        if seconds_remaining(clock()) < 1 or power() != "AC":
            return 0
        duration = int(seconds_remaining(clock()))
        if duration < 1:
            return 0
        child = popen(["/usr/bin/caffeinate", "-i", "-t", str(duration), "-w", str(os.getpid())],
                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, shell=False)
        while child.poll() is None:
            remaining = seconds_remaining(clock())
            if remaining <= 0 or power() != "AC":
                break
            # A power read has a two-second timeout; two-second sleeps bound checks below five seconds.
            sleep(min(2, remaining))
        return 0
    except Exception:
        print("Workday idle-sleep assertion unavailable; no continued assertion requested.")
        return 1
    finally:
        if child is not None:
            stop(child)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    allowed = seconds_remaining(local_now()) > 0
    if not allowed and not args.check:
        return 0
    source = power_source()
    if args.check:
        print(json.dumps({"timezone": "Asia/Kolkata", "in_window": allowed, "power": source,
                          "intent": "prevent_idle_system_sleep" if allowed and source == "AC" else "no_assertion"}))
        return 0
    if not allowed or source != "AC":
        return 0
    def interrupted(signum, frame):
        raise SystemExit(0)
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        with instance_lock("~/.openwork/workday-awake.lock") as acquired:
            return hold_awake() if acquired else 0
    except Exception:
        print("Workday awake helper unavailable; no assertion started.")
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
