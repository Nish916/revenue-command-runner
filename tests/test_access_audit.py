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
        report = audit.audit(self.home, lambda p, e, t: (200, {}, None))
        for provider in report["providers"].values():
            for result in provider["endpoints"].values():
                self.assertNotIn("data", result)

    def test_cloud_revenue_command_dashboard_integration(self):
        report = audit.audit(self.home, self.valid)
        self.assertIn("providers", report)
        self.assertIn("dealwork", report["providers"])
        self.assertIn("toku", report["providers"])
        self.assertEqual(report["providers"]["dealwork"]["state"], "AUTHENTICATED_READ_VERIFIED")
        self.assertEqual(report["providers"]["toku"]["state"], "AUTHENTICATED_READ_VERIFIED")