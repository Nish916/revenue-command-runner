import contextlib
from datetime import datetime, timezone
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
    def test_continuous_gate_and_aware_clock(self):
        for value in (moment(0), moment(7, 59, 59), moment(8), moment(19, 59, 59), moment(20), moment(23, 59, 59)):
            self.assertGreater(gate.seconds_remaining(value), 0)
            self.assertGreater(gate.seconds_remaining(value.astimezone(timezone.utc)), 0)
        with self.assertRaises(ValueError):
            gate.seconds_remaining(datetime(2026, 9, 28, 8))

    def test_gate_executes_all_day_without_shell(self):
        command = ["tool", "one argument", "$(must-stay-literal)"]
        for hour in (0, 7, 8, 20, 23):
            with self.subTest(hour=hour), patch.object(gate, "local_now", return_value=moment(hour)), patch.object(gate.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as run:
                self.assertEqual(gate.main(["--"] + command), 7)
                run.assert_called_once_with(command, shell=False, check=False)

    def test_check_modes_never_execute_or_acquire_assertion(self):
        with patch.object(gate, "local_now", return_value=moment(23)), patch.object(gate.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gate.main(["--check"]), 0)
            run.assert_not_called()
        status = json.loads(output.getvalue())
        self.assertTrue(status["in_window"])
        self.assertEqual(status["mode"], "continuous_24h")
        with patch.object(awake, "power_source", return_value="AC"), patch.object(awake, "instance_lock") as lock, patch.object(awake, "hold_awake") as hold, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(awake.main(["--check"]), 0)
            lock.assert_not_called()
            hold.assert_not_called()
        status = json.loads(output.getvalue())
        self.assertTrue(status["in_window"])
        self.assertEqual(status["mode"], "continuous_24h")
        self.assertEqual(status["intent"], "prevent_idle_system_sleep")

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

    def test_battery_and_unknown_fail_closed(self):
        for source in ("BATTERY", "UNKNOWN"):
            popen = Mock()
            self.assertEqual(awake.hold_awake(clock=lambda: moment(3), power=lambda: source, popen=popen), 0)
            popen.assert_not_called()

    def test_disconnect_releases_tracked_child(self):
        for disconnected in ("BATTERY", "UNKNOWN"):
            sources = iter(["AC", "AC", disconnected])
            child = Mock()
            child.poll.return_value = None
            popen = Mock(return_value=child)
            sleep = Mock()
            self.assertEqual(awake.hold_awake(clock=lambda: moment(23), power=lambda: next(sources), sleep=sleep, popen=popen), 0)
            command = popen.call_args.args[0]
            self.assertEqual(command, ["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())])
            self.assertFalse(popen.call_args.kwargs["shell"])
            sleep.assert_called_once_with(2)
            child.terminate.assert_called_once()
            child.wait.assert_called_once_with(timeout=2)

    def test_continuous_ac_has_no_time_limit(self):
        sources = iter(["AC", "AC", "BATTERY"])
        child = Mock()
        child.poll.return_value = None
        popen = Mock(return_value=child)
        sleep = Mock()
        self.assertEqual(awake.hold_awake(clock=lambda: moment(23, 59, 59), power=lambda: next(sources), sleep=sleep, popen=popen), 0)
        command = popen.call_args.args[0]
        self.assertNotIn("-t", command)
        self.assertEqual(command[-2:], ["-w", str(os.getpid())])
        sleep.assert_called_once_with(2)

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
