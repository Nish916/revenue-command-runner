import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import agent402_refresh as agent


class Agent402Tests(unittest.TestCase):
    def test_canonical_origin_and_child_urls_but_not_spoofs(self):
        for url in (agent.ORIGIN, agent.ORIGIN + "/", agent.ORIGIN + "/api/evaluate?version=2"):
            self.assertEqual(agent.index_presence({"resources": [{"url": url}]}), "CONFIRMED")
        for url in ("https://nexuseval.vercel.app.evil.example/api", "https://nexuseval.vercel.app@evil.example/", "https://evil.example/?url=" + agent.ORIGIN, "https://other.vercel.app/nexuseval.vercel.app", "not-a-url", "http://nexuseval.vercel.app"):
            self.assertEqual(agent.index_presence({"resources": [{"url": url}]}), "NOT_CONFIRMED")
        self.assertEqual(agent.index_presence({"resources": [{"description": agent.ORIGIN}]}), "NOT_CONFIRMED")

    def test_empty_recognized_index_differs_from_unknown_schema(self):
        self.assertEqual(agent.index_presence({"data": {"items": []}}), "NOT_CONFIRMED")
        self.assertEqual(agent.index_presence({"unknown": []}), "UNKNOWN")
        self.assertEqual(agent.index_presence({"requestedOrigin": agent.ORIGIN}), "UNKNOWN")
        self.assertEqual(agent.index_presence({"data": {"items": [{"origin": agent.ORIGIN}]}}), "CONFIRMED")

    def test_partial_index_no_match_is_unknown_but_positive_match_confirms(self):
        for tools, expected in (([{"url": "https://other.example/api"}], "UNKNOWN"),
                                ([{"resource": agent.ORIGIN + "/api/evaluate"}], "CONFIRMED")):
            payload = {"complete": False, "page": 0, "perPage": 100,
                       "sellerCount": 4578, "pages": 46, "indexState": "ready",
                       "sellers": [{"origin": "self", "tools": tools}]}
            self.assertEqual(agent.index_presence(payload), expected)
            responses = [(200, {}, None), (200, {"listed": True}, None), (200, payload, None)]
            report = agent.refresh(requester=lambda *args: responses.pop(0))
            self.assertEqual(report["listing_state"], expected)
            self.assertEqual(report["index"]["checked_page"], 0)
            self.assertEqual(report["index"]["total_pages"], 46)
            self.assertIs(report["index"]["complete"], False)
            self.assertNotIn("sellerCount", report["index"])
            if expected == "UNKNOWN":
                self.assertEqual(report["index"]["reason"], "PARTIAL_INDEX")
            else:
                self.assertNotIn("reason", report["index"])

    def test_index_metadata_requires_exact_safe_types(self):
        payload = {"complete": "false", "page": True, "pages": -1, "sellers": []}
        responses = [(200, {}, None), (200, {}, None), (200, payload, None)]
        report = agent.refresh(requester=lambda *args: responses.pop(0))
        for key in ("complete", "checked_page", "total_pages"):
            self.assertNotIn(key, report["index"])

    def test_registration_200_alone_never_confirms_listing(self):
        responses = [(200, {"resources": [{}, {}]}, None), (200, {"ok": True}, None), (200, {"resources": []}, None)]
        with patch.object(agent, "request", side_effect=responses) as request:
            report = agent.refresh()
        self.assertEqual(request.call_args_list, [(('GET', agent.MANIFEST),), (('POST', agent.REGISTER),), (('GET', agent.INDEX),)])
        self.assertEqual(report["manifest"]["resource_count"], 2)
        self.assertEqual(report["registration"]["state"], "UNKNOWN")
        self.assertNotIn("listed", report["registration"])
        self.assertEqual(report["listing_state"], "NOT_CONFIRMED")

    def test_boolean_acknowledgement_and_index_are_independent(self):
        responses = [(200, {}, None), (200, {"listed": True}, None), (503, None, "HTTP_ERROR")]
        report = agent.refresh(requester=lambda *args: responses.pop(0))
        self.assertTrue(report["registration"]["listed"])
        self.assertEqual(report["registration"]["state"], "CONFIRMED")
        self.assertEqual(report["listing_state"], "UNKNOWN")
        responses = [(200, {}, None), (200, {"listed": False}, None), (200, [agent.ORIGIN + "/api/test"], None)]
        report = agent.refresh(requester=lambda *args: responses.pop(0))
        self.assertEqual(report["registration"]["state"], "NOT_CONFIRMED")
        self.assertEqual(report["listing_state"], "CONFIRMED")

    def test_unverified_manifest_prevents_post_but_still_checks_index(self):
        with patch.object(agent, "request", side_effect=[(404, None, "HTTP_ERROR"), (200, [], None)]) as request:
            report = agent.refresh()
        self.assertEqual([call.args[0] for call in request.call_args_list], ["GET", "GET"])
        self.assertIsNone(report["registration"]["http_status"])
        self.assertNotIn("resource_count", report["manifest"])

    def test_fixed_registration_payload_and_no_credentials_or_redirects(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return b'{"listed":false}'
        with patch.object(agent, "build_opener") as build:
            build.return_value.open.return_value = Response()
            self.assertEqual(agent.request("POST", agent.REGISTER), (200, {"listed": False}, None))
            call = build.return_value.open.call_args
            req = call.args[0]
            self.assertEqual(req.full_url, agent.REGISTER)
            self.assertEqual(req.get_method(), "POST")
            self.assertEqual(json.loads(req.data), {"origin": agent.ORIGIN})
            self.assertIsNone(req.get_header("Authorization"))
            self.assertEqual(call.kwargs["timeout"], agent.TIMEOUT)
            self.assertIsInstance(build.call_args.args[0], agent.NoRedirect)
        self.assertEqual(agent.request("POST", agent.INDEX), (None, None, "DISALLOWED_REQUEST"))

    def test_errors_are_sanitized_and_redirects_rejected(self):
        with patch.object(agent, "build_opener") as build:
            build.return_value.open.side_effect = HTTPError(agent.REGISTER, 302, "sensitive-body", {}, None)
            self.assertEqual(agent.request("POST", agent.REGISTER), (302, None, "REDIRECT_REJECTED"))
            build.return_value.open.side_effect = RuntimeError("sensitive-body")
            self.assertEqual(agent.request("GET", agent.INDEX), (None, None, "READ_FAILED"))

    def test_24_hour_gate_and_skip_preserves_original_snapshot(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "refresh.json"
            for hours, expected in ((1, True), (23.9, True), (24, False), (25, False), (-1, False)):
                output.write_text(json.dumps({"checked_at": (now - timedelta(hours=hours)).isoformat()}))
                self.assertEqual(agent.recently_attempted(output, now), expected)
            output.write_text(json.dumps({"checked_at": now.isoformat(), "listing_state": "UNKNOWN"}))
            before = output.read_bytes()
            with patch.object(sys, "argv", ["agent402_refresh", "--output", str(output)]), patch.object(agent, "refresh") as refresh, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(agent.main(), 0)
                refresh.assert_not_called()
            self.assertEqual(before, output.read_bytes())
            output.write_text("broken-json")
            self.assertFalse(agent.recently_attempted(output, now))

    def test_failed_attempt_is_saved_and_does_not_fail_scheduler(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "refresh.json"
            with patch.object(sys, "argv", ["agent402_refresh", "--output", str(output)]), patch.object(agent, "request", return_value=(None, None, "READ_FAILED")), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(agent.main(), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["listing_state"], "UNKNOWN")
            self.assertEqual(report["index"]["http_status"], None)
            self.assertTrue(agent.recently_attempted(output, datetime.now(timezone.utc)))


if __name__ == "__main__":
    unittest.main()
