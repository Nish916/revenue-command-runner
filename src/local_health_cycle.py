#!/usr/bin/env python3
"""Run account reads hourly and public listing refresh at most daily."""
from datetime import datetime, timezone
import fcntl
from pathlib import Path
import subprocess
import sys

from access_audit import save


def main():
    state = Path.home() / ".openwork"
    state.mkdir(mode=0o700, exist_ok=True)
    source = Path(__file__).resolve().parent
    with (state / "access-audit.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        report = {"started_at": datetime.now(timezone.utc).isoformat(), "steps": {}}
        # Agent402 public refresh moved to the daily cloud workflow; avoid duplicate POSTs.
        for name, limit in (("access_audit", 85),):
            try:
                result = subprocess.run(
                    [sys.executable, str(source / (name + ".py"))],
                    capture_output=True, text=True, timeout=limit, check=False)
                report["steps"][name] = {"exit_code": result.returncode}
            except subprocess.TimeoutExpired:
                report["steps"][name] = {"state": "TIMEOUT"}
            except Exception:
                report["steps"][name] = {"state": "EXECUTION_FAILED"}
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["semantics"] = "Process health only; inspect individual snapshots for access, listing or income evidence."
        save(report, state / "access-cycle.json")
        return 0 if all(x.get("exit_code") == 0 for x in report["steps"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
