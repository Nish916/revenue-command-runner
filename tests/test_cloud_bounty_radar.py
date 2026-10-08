"""No-network regression tests for cloud bounty discovery."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import cloud_bounty_radar as radar


def issue(title, body="", *, author="maintainer", assoc="OWNER", number=8, **more):
    record = {
        "state": "open",
        "html_url": f"https://github.com/example/project/issues/{number}",
        "title": title,
        "body": body,
        "user": {"login": author},
        "author_association": assoc,
        "assignees": [],
        "comments": 2,
        "updated_at": "2026-10-08T10:00:00Z",
    }
    record.update(more)
    return record


class RadarTests(unittest.TestCase):
    def test_parses_explicit_rewards_only(self):
        for text, expected in (
            ("[Bounty $3,000] Sampling fix", 3000),
            ("Reward: 75 USDC", 75),
            ("A $780 USD bounty", 780),
            ("Bounty worth $1.5k", 1500),
        ):
            with self.subTest(text=text):
                self.assertEqual(radar.amount_and_evidence(text)[0], expected)
        for text in ("bounty-2026-0304 completed", "the invoice is $5,100", "set balance to 240 USDC", "bounty 50", "bounty: $25"):
            with self.subTest(text=text):
                self.assertEqual(radar.amount_and_evidence(text)[0], 0)

    def test_rejects_user_issues_assigned_and_payout_noise(self):
        cases = (
            issue("[Bounty $100]", author="Nish916"),
            issue("[Bounty $100]", assignees=[{"login":"other"}]),
            issue("[Bounty $100]", body="This was assigned to @someone already"),
            issue("Bounty payout system broken: $1,500 stuck in review"),
            issue("[Bounty $100]", state="closed"),
            issue("[Bounty $100]", pull_request={"url":"https://example.org"}),
            issue("[Bounty $100]", html_url="https://github.com/Nish916/self/issues/8"),
        )
        for record in cases:
            self.assertIsNone(radar.parse_issue(record), record["title"])

    def test_maintainer_signal_still_unverified_funding(self):
        result=radar.parse_issue(issue("Small fix", "## Bounty\nBounty: $300 USD", assoc="MEMBER"))
        self.assertEqual(result["amount_advertised"], 300)
        self.assertTrue(result["maintainer_authored"])
        self.assertEqual(result["funding"], "NOT_VERIFIED")
        self.assertEqual(result["action"], "VERIFY_PAYER_RULES_AND_ELIGIBILITY")

    def test_dedup_and_downrank_external_claim(self):
        maintainer=issue("[Bounty $250] verified deliverable", number=2)
        contributor=issue("[Bounty $600] open task", assoc="NONE", number=3)
        calls=[]
        def fake(*args):
            calls.append(args)
            if args[0]=="search/issues":
                return {"items": [maintainer, contributor, maintainer]}
            if args[0]=="repos/example/project":
                return {"archived":False,"stargazers_count":10,"owner":{"type":"Organization"}}
            raise AssertionError(args)
        r=radar.scan(fake)
        self.assertEqual(r["candidate_count"],2)
        self.assertEqual(r["top"][0]["number"],2)
        self.assertEqual(r["top"][1]["review_priority"],"LOW_CONFIDENCE")
        self.assertEqual(len([c for c in calls if c[0]=="repos/example/project"]),1)

    def test_fails_closed_on_search_outage(self):
        def failed(*args):
            raise TimeoutError()
        with self.assertRaisesRegex(RuntimeError,"All GitHub bounty searches failed"):
            radar.scan(failed)


if __name__=="__main__":
    unittest.main()
