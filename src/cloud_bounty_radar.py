#!/usr/bin/env python3
"""Public GitHub bounty scout. Advisory only: no payouts, claims or submissions."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

GH = shutil.which("gh") or "gh"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get("BOUNTY_RADAR_OUTPUT", ROOT / "bounty_radar.json"))
OWNER = os.environ.get("BOUNTY_GITHUB_USER", "Nish916").lower()
SINCE = (datetime.now(timezone.utc) - timedelta(days=45)).date().isoformat()
QUERIES = (
    f'is:issue is:open label:bounty updated:>={SINCE}',
    f'is:issue is:open in:title bounty updated:>={SINCE}',
    f'is:issue is:open in:title reward updated:>={SINCE}',
    f'is:issue is:open "USDC bounty" updated:>={SINCE}',
)
MIN_REWARD = 50.0
MAX_REWARD = 100000.0
BAD_REPO = re.compile(r'(?:bounty-plaza|rustchain-bounties|claim[-_]?tracker|earnings[-_]?radar|bounty[-_]?radar|gh-disc-)', re.I)
BAD_TITLE = re.compile(r'(?:payout request|payout system broken|consolidated claim|claiming this bounty|claiming bounty for|completed verification|bounty qualification|qualification:|stuck in review|reimbursement)', re.I)
ASSIGNED = re.compile(r'\b(?:assigned|awarded)\s+to\s+(?:\[)?@?[A-Za-z0-9-]+', re.I)
REWARD = (
    re.compile(r'(?i)\b(?:bounty|reward)(?:\s+(?:of|worth|is))?\s*[:=\-]?\s*(?:USD\s*)?\$\s*([0-9][0-9,]*(?:\.\d+)?)([kKmM]?)\b'),
    re.compile(r'(?i)\b(?:bounty|reward)(?:\s+(?:of|worth|is))?\s*[:=\-]?\s*([0-9][0-9,]*(?:\.\d+)?)([kKmM]?)\s*(?:USD|USDC)\b'),
    re.compile(r'(?i)\$\s*([0-9][0-9,]*(?:\.\d+)?)([kKmM]?)\s*(?:USD|USDC)?\s+(?:gross\s+)?(?:bounty|reward)\b'),
)
CONFIDENT_ASSOCIATION = frozenset(("OWNER", "MEMBER", "COLLABORATOR"))


def gh_json(*arguments):
    return json.loads(subprocess.check_output(
        [GH, "api", "-X", "GET", *arguments],
        stderr=subprocess.PIPE, text=True, timeout=30
    ))


def amount_and_evidence(text):
    matches = []
    for pattern in REWARD:
        for match in pattern.finditer(text[:1500]):
            try:
                amount = float(match.group(1).replace(",", ""))
                scale = (match.group(2) or "").lower()
                if scale == "k":
                    amount *= 1000
                elif scale == "m":
                    amount *= 1000000
                if MIN_REWARD <= amount <= MAX_REWARD:
                    matches.append((amount, match.group(0).strip()[:90]))
            except (TypeError, ValueError):
                pass
    return max(matches, key=lambda item: item[0]) if matches else (0.0, None)


def parse_issue(item):
    if item.get("state") != "open" or item.get("pull_request"):
        return None
    url = str(item.get("html_url") or "")
    match = re.fullmatch(r'https://github\.com/([^/]+/[^/]+)/issues/(\d+)', url)
    if not match:
        return None
    repo, number = match.groups()
    title = str(item.get("title") or "")
    body = str(item.get("body") or "")
    author = str((item.get("user") or {}).get("login") or "")
    if author.lower() == OWNER or repo.split("/")[0].lower() == OWNER:
        return None
    if BAD_REPO.search(repo) or BAD_TITLE.search(title):
        return None
    assignees = [a.get("login") for a in item.get("assignees", []) if isinstance(a, dict)]
    if assignees and OWNER not in [str(a).lower() for a in assignees]:
        return None
    if ASSIGNED.search(body[:1600]) and not assignees:
        return None
    amount, evidence = amount_and_evidence(title + "\n" + body[:1300])
    if not evidence:
        return None
    assoc = str(item.get("author_association") or "NONE")
    return {
        "repo": repo,
        "number": int(number),
        "title": title[:180],
        "url": url,
        "amount_advertised": amount,
        "reward_evidence": evidence,
        "author_association": assoc,
        "maintainer_authored": assoc in CONFIDENT_ASSOCIATION,
        "updated_at": item.get("updated_at"),
        "comments": item.get("comments", 0),
        "funding": "NOT_VERIFIED",
        "award": "NOT_VERIFIED",
        "action": "VERIFY_PAYER_RULES_AND_ELIGIBILITY",
    }


def scan(request=gh_json):
    found, errors = {}, []
    for query in QUERIES:
        try:
            payload = request("search/issues", "-f", "q=" + query, "-f", "per_page=100")
            for item in payload.get("items", []):
                if item.get("html_url"):
                    found[item["html_url"]] = item
        except Exception as exc:
            errors.append(type(exc).__name__)
    if errors and len(errors) == len(QUERIES):
        raise RuntimeError("All GitHub bounty searches failed; refusing to publish a stale-success snapshot")
    candidates = [parsed for item in found.values() if (parsed := parse_issue(item))]
    candidates.sort(key=lambda x: (int(x["maintainer_authored"]), x["amount_advertised"], x["updated_at"] or ""), reverse=True)
    credible = []
    repo_cache = {}
    for item in candidates[:30]:
        repo = item["repo"]
        if repo not in repo_cache:
            try:
                meta = request("repos/" + repo)
                repo_cache[repo] = {
                    "archived": bool(meta.get("archived", False)),
                    "stars": int(meta.get("stargazers_count") or 0),
                    "owner_type": str((meta.get("owner") or {}).get("type") or ""),
                }
            except Exception:
                repo_cache[repo] = None
        meta = repo_cache[repo]
        if not meta or meta["archived"]:
            continue
        item.update({"repo_stars": meta["stars"], "repo_owner_type": meta["owner_type"]})
        item["review_priority"] = "CHECK_FIRST" if item["maintainer_authored"] and meta["stars"] >= 5 else "LOW_CONFIDENCE"
        credible.append(item)
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "mode": "CLOUD_PUBLIC_DISCOVERY_ONLY",
        "source": "GitHub public issues",
        "searches_succeeded": len(QUERIES) - len(errors),
        "searches_failed": len(errors),
        "raw_issues": len(found),
        "reward_signals": len(candidates),
        "candidate_count": len(credible),
        "top": credible[:20],
        "truth_rule": "Published amounts are advertisements, never approved receivables. Check payer, eligibility, AI rules and actual funding before working or claiming.",
    }


def main():
    report = scan()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(OUTPUT)
    print(json.dumps({
        "scanned_at": report["scanned_at"],
        "raw_issues": report["raw_issues"],
        "reward_signals": report["reward_signals"],
        "candidate_count": report["candidate_count"],
        "searches_failed": report["searches_failed"],
        "mode": report["mode"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
