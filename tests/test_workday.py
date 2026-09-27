import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import workday_gate as gate
import workday_awake as awake


def moment(hour, minute=0, second=0):
    return datetime(2026, 9, 28, hour, minute, second, tzinfo=gate.ZONE)


class WorkdayTests(unittest.TestCase):
    def test_boundaries_and_nonlocal_aware_clock(self):
        for value, expected in ((moment(7, 59, 59), 0), (moment(8), 43200),
                                (moment(19, 59, 59), 1), (moment(20), 0)):
            self.assertEqual(gate.seconds_remaining(value), expected)
            self.assertEqual(gate.seconds_remaining(value.astimezone(timezone.utc)), expected)
        with self.assertRaises(ValueError):
            gate.seconds_remaining(datetime(2026, 9, 28, 8))

    def test_gate_skips_outside_and_executes_arguments_without_shell(self):
        command = ["tool", "one argument", "$(must-stay-literal)"]
        with patch.object(gate, "local_now", return_value=moment(7)), patch.object(gate.subprocess, "run") as run:
            self.assertEqual(gate.main(["--"] + command), 0)
            run.assert_not_called()
        with patch.object(gate, "local_now", return_value=moment(8)), patch.object(gate.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as run:
            self.assertEqual(gate.main(["--"] + command), 7)
            run.assert_called_once_with(command, shell=False, check=False)

    def test_check_modes_never_execute_or_acquire_assertion(self):
        with patch.object(gate, "local_now", return_value=moment(10)), patch.object(gate.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gate.main(["--check"]), 0)
            run.assert_not_called()
        self.assertTrue(json.loads(output.getvalue())["in_window"])
        with patch.object(awake, "local_now", return_value=moment(10)), patch.object(awake, "power_source", return_value="AC"), patch.object(awake, "instance_lock") as lock, patch.object(awake, "hold_awake") as hold, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(awake.main(["--check"]), 0)
            lock.assert_not_called()
            hold.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["intent"], "prevent_idle_system_sleep")

    def test_power_detection_accepts_only_successful_exact_ac_header(self):
        for stdout, returncode, expected in (("Now drawing from 'AC Power'\nprivate battery details", 0, "AC"),
                                            ("Now drawing from 'Battery Power'", 0, "BATTERY"),
                                            ("Now drawing from 'UPS Power'", 0, "UNKNOWN"),
                                            ("unrecognized\nNow drawing from 'AC Power'", 0, "UNKNOWN"),
                                            ("Now drawing from 'AC Power'", 1, "UNKNOWN")):
            with patch.object(awake.subprocess, "run", return_value=SimpleNamespace(stdout=stdout, returncode=returncode)) as run:
                self.assertEqual(awake.power_source(), expected)
                self.assertEqual(run.call_args.kwargs["timeout"], 2)
        with patch.object(awake.subprocess, "run", side_effect=subprocess.TimeoutExpired("pmset", 2)):
            self.assertEqual(awake.power_source(), "UNKNOWN")

    def test_battery_unknown_and_outside_window_fail_closed(self):
        for source, now in (("BATTERY", moment(9)), ("UNKNOWN", moment(9)), ("AC", moment(20))):
            popen = Mock()
            self.assertEqual(awake.hold_awake(clock=lambda: now, power=lambda: source, popen=popen), 0)
            popen.assert_not_called()

    def test_disconnect_and_detection_failure_release_tracked_child(self):
        for disconnected in ("BATTERY", "UNKNOWN"):
            sources = iter(["AC", "AC", disconnected])
            child = Mock()
            child.poll.return_value = None
            popen = Mock(return_value=child)
            sleep = Mock()
            self.assertEqual(awake.hold_awake(clock=lambda: moment(19), power=lambda: next(sources), sleep=sleep, popen=popen), 0)
            command = popen.call_args.args[0]
            self.assertEqual(command, ["/usr/bin/caffeinate", "-i", "-t", "3600", "-w", str(os.getpid())])
            self.assertFalse(popen.call_args.kwargs["shell"])
            sleep.assert_called_once_with(2)
            child.terminate.assert_called_once()
            child.wait.assert_called_once_with(timeout=2)

    def test_end_window_bounds_lifetime_and_releases_child(self):
        current = [moment(19, 59, 57)]
        sleeps = []
        def sleep(seconds):
            sleeps.append(seconds)
            current[0] += timedelta(seconds=seconds)
        child = Mock()
        child.poll.return_value = None
        popen = Mock(return_value=child)
        self.assertEqual(awake.hold_awake(clock=lambda: current[0], power=lambda: "AC", sleep=sleep, popen=popen), 0)
        self.assertEqual(popen.call_args.args[0][2:4], ["-t", "3"])
        self.assertEqual(sum(sleeps), 3)
        self.assertTrue(all(delay <= 2 for delay in sleeps))
        child.terminate.assert_called_once()

    def test_interruption_and_unresponsive_child_cleanup(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("caffeinate", 2), 0]
        with self.assertRaises(KeyboardInterrupt):
            awake.hold_awake(clock=lambda: moment(9), power=lambda: "AC", sleep=Mock(side_effect=KeyboardInterrupt), popen=Mock(return_value=child))
        child.terminate.assert_called_once()
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)

    def test_advisory_lock_excludes_duplicate_helper_without_pid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "awake.lock"
            with awake.instance_lock(path) as first:
                self.assertTrue(first)
                with awake.instance_lock(path) as second:
                    self.assertFalse(second)
            with awake.instance_lock(path) as reacquired:
                self.assertTrue(reacquired)
            self.assertEqual(path.read_bytes(), b"")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
