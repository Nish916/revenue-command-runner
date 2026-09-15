#!/usr/bin/env python3
import json, os, urllib.request, pathlib

root = pathlib.Path(__file__).resolve().parents[1]
result = json.loads((root / "result.json").read_text())
token = os.environ["GITHUB_TOKEN"]

prompt = """You are the cloud revenue command brain. Use only the supplied evidence. Goal: maximize legitimate externally funded settlement for an India-based operator while minimizing zero-revenue stretches. Never count claims, bids, PRs, listings, self-transfers, 402s, or headline rewards as revenue. No trading, gambling, deposits/stakes, fake traffic, spam, identity rental, or unauthorized exploitation.

Given the live evidence below:
1) identify the single closest-to-cash verified lane,
2) identify the highest expected-value opportunity worth deeper verification,
3) give the next three actions that can be done without inventing facts,
4) park/reject stale or suspicious lanes,
5) state the exact evidence needed before calling anything paid.

Be concise. Label every statement VERIFIED, INFERENCE, or UNVERIFIED. Do not fabricate URLs, budgets, acceptance, or payment.

LIVE EVIDENCE:
""" + json.dumps(result, indent=2)

payload = {
  "model": "openai/gpt-4o",
  "messages": [
    {"role": "system", "content": "Evidence first. Be economically rigorous and concise."},
    {"role": "user", "content": prompt}
  ],
  "temperature": 0.2,
  "max_tokens": 900
}
req = urllib.request.Request(
  "https://models.github.ai/inference/chat/completions",
  data=json.dumps(payload).encode(),
  headers={
    "Content-Type":"application/json",
    "Authorization":"Bearer " + token,
    "User-Agent":"revenue-command-runner/1.0"
  },
  method="POST"
)
try:
  with urllib.request.urlopen(req, timeout=60) as r:
    data = json.loads(r.read().decode())
  text = data["choices"][0]["message"]["content"]
except Exception as e:
  text = "AI planning unavailable: " + repr(e)

(root / "plan.md").write_text(text)
print(text)
