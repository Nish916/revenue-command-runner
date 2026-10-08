import contextlib
import io
import json
from pathlib import Path
import signal
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import access_audit as audit


SECRET = "private-test-token-never-print"
PAYLOADS = {
    ("dealwork", "wallet"): {"data": {"available": "0.070000", "locked": "12.00", "currency": "USD", "accountId": "private-id"}},
    ("dealwork", "contracts"): {"data": [{"customer": "private-person"}]},
    ("dealwork", "pending_requests"): {"data": []},
    ("toku", "agent"): {"agent": {"status": "active", "jobsCompleted": 3, "services": [{"id": "private-id"}]}},
    ("toku", "wallet"): {"balanceCents": 1234, "transactions": [{"secret": SECRET}]},
    ("toku", "connect"): {"connected": True, "onboarded": True, "chargesEnabled": False, "payoutsEnabled": False},
    ("toku", "jobs"): {"jobs": []},
}


class Response:
    status = 200

    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def read(self, limit):
        return self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AccessAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / ".openwork").mkdir()
        (self.home / ".toku-worker").mkdir()
        (self.home / ".openwork/credentials.json").write_text(json.dumps({"apiKey": SECRET, "agentAccountId": "private-id", "baseUrl": "https://api.dealwork.ai"}))
        (self.home / ".toku-worker/api_key").write_text(SECRET + "\n")

    def valid(self, provider, endpoint, token):
        self.assertEqual(token, SECRET)
        return 200, PAYLOADS[(provider, endpoint)], None

    def test_normalization_preserves_units_and_redacts_other_fields(self):
        report = audit.audit(self.home, self.valid)
        providers = report["providers"]
        self.assertEqual(providers["dealwork"]["state"], "AUTHENTICATED_READ_VERIFIED")
        self.assertEqual(providers["dealwork"]["endpoints"]["wallet"]["data"], {"available": "0.070000", "locked": "12.00", "currency": "USD"})
        self.assertEqual(providers["toku"]["endpoints"]["wallet"]["data"]["balance_cents"], 1234)
        self.assertFalse(providers["toku"]["endpoints"]["connect"]["data"]["payoutsEnabled"])
        self.assertEqual(providers["dealwork"]["endpoints"]["contracts"]["data"], {"records_returned": 1})
        text = json.dumps(report)
        for private in (SECRET, "private-id", "private-person"):
            self.assertNotIn(private, text)

    def test_non_200_has_no_zero_balances_even_with_json_body(self):
        report = audit.audit(self.home, lambda *args: (401, PAYLOADS[("dealwork", "wallet")], None))
        for provider in report["providers"].values():
            self.assertEqual(provider["state"], "UNKNOWN")
            for result in provider["endpoints"].values():
                self.assertEqual(result["state"], "UNKNOWN")
                self.assertEqual(result["http_status"], 401)
                self.assertNotIn("data", result)

    def test_missing_balance_does_not_default_to_zero(self):
        def get(provider, endpoint, token):
            if endpoint == "wallet":
                return 200, {"data": {"locked": "0", "currency": "USD"}, "transactions": []}, None
            return self.valid(provider, endpoint, token)
        report = audit.audit(self.home, get)
        for provider in report["providers"].values():
            result = provider["endpoints"]["wallet"]
            self.assertEqual(result["reason"], "INVALID_RESPONSE")
            self.assertNotIn("data", result)

    def test_missing_or_malformed_credentials_never_make_requests_or_leak(self):
        for malformed in (None, '{"apiKey":"' + SECRET, json.dumps({"apiKey": SECRET + "\r\nInjected: value"})):
            with self.subTest(malformed=malformed is None):
                path = self.home / ".openwork/credentials.json"
                if malformed is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(malformed)
                (self.home / ".toku-worker/api_key").unlink(missing_ok=True)
                with patch.object(audit, "fetch") as fetch:
                    report = audit.audit(self.home)
                    fetch.assert_not_called()
                self.assertNotIn(SECRET, json.dumps(report))
                self.assertTrue(all(p["state"] == "UNKNOWN" for p in report["providers"].values()))

    def test_unapproved_origin_is_rejected_before_io(self):
        (self.home / ".openwork/credentials.json").write_text(json.dumps({"apiKey": SECRET, "baseUrl": "https://dealwork.ai.attacker.example"}))
        (self.home / ".toku-worker/api_key").unlink()
        with patch.object(audit, "fetch") as fetch:
            report = audit.audit(self.home)
            fetch.assert_not_called()
        self.assertEqual(report["providers"]["dealwork"]["endpoints"]["wallet"]["reason"], "UNAPPROVED_ORIGIN")

    def test_redirect_handler_rejects_every_destination(self):
        request = Request("https://dealwork.ai/api/v1/wallet/balance", headers={"Authorization": "Bearer " + SECRET})
        for url in ("https://attacker.example/", "https://dealwork.ai/other"):
            response_body = io.BytesIO(b"private response")
            with self.assertRaises(HTTPError) as caught:
                audit.NoRedirect().redirect_request(request, response_body, 302, "Found", {}, url)
            caught.exception.close()
            self.assertTrue(response_body.closed)

    def test_get_only_fixed_urls_with_timeout_and_no_redirect_handler(self):
        observed = []
        def open_request(request, timeout):
            observed.append(request)
            self.assertEqual(timeout, audit.TIMEOUT)
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            self.assertEqual(request.get_header("Authorization"), "Bearer " + SECRET)
            for provider, (origin, paths) in audit.ROUTES.items():
                for endpoint, path in paths.items():
                    if request.full_url == origin + path:
                        return Response(PAYLOADS[(provider, endpoint)])
            self.fail("Unexpected network destination")
        with patch.object(audit, "build_opener") as build:
            build.return_value.open.side_effect = open_request
            report = audit.audit(self.home)
            self.assertEqual(len(observed), 7)
            self.assertTrue(all(isinstance(call.args[0], audit.NoRedirect) for call in build.call_args_list))
        self.assertTrue(all(p["state"] == "AUTHENTICATED_READ_VERIFIED" for p in report["providers"].values()))

    def test_transport_errors_are_sanitized_and_redirects_recorded(self):
        with patch.object(audit, "build_opener") as build:
            for error, expected in [(RuntimeError(SECRET), (None, None, "READ_FAILED")),
                                    (HTTPError("https://dealwork.ai", 302, SECRET, {}, None), (302, None, "REDIRECT_REJECTED"))]:
                build.return_value.open.side_effect = error
                self.assertEqual(audit.fetch("dealwork", "wallet", SECRET), expected)

    def test_boolean_or_nonfinite_balances_rejected(self):
        for payload in ({"balanceCents": True, "transactions": []}, {"balanceCents": None, "transactions": []}):
            with self.assertRaises(ValueError):
                audit.normalize("toku", "wallet", payload)
        with self.assertRaises(ValueError):
            audit.normalize("dealwork", "wallet", {"data": {"available": "NaN", "locked": "0", "currency": "USD"}})

    def test_atomic_private_save_and_sanitized_cli(self):
        output = self.home / "reports/audit.json"
        report = audit.audit(self.home, self.valid)
        audit.save(report, output)
        self.assertEqual(json.loads(output.read_text()), report)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(output.parent.stat().st_mode), 0o700)
        self.assertEqual(list(output.parent.iterdir()), [output])
        with patch.object(audit, "audit", return_value=report), patch.object(sys, "argv", ["access_audit", "--output", str(output)]), contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(audit.main(), 0)
        self.assertNotIn(SECRET, stdout.getvalue())
        self.assertIn("AUTHENTICATED_READ_VERIFIED", stdout.getvalue())

    @unittest.skipUnless(hasattr(signal, "setitimer"), "Unix deadline")
    def test_wall_clock_deadline_interrupts_a_stalled_body(self):
        class Stalled(Response):
            def read(self, limit):
                signal.pause()
        with patch.object(audit, "TIMEOUT", 0.02), patch.object(audit, "build_opener") as build:
            build.return_value.open.return_value = Stalled({})
            self.assertEqual(audit.fetch("toku", "wallet", SECRET), (200, None, "READ_FAILED"))


if __name__ == "__main__":
    unittest.main()
