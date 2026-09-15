#!/usr/bin/env python3
import json, os, pathlib, urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
result = json.loads((root / "result.json").read_text())

def deterministic():
    opps = result.get("opportunities", [])
    cognitive = (result.get("submitted") or {}).get("cognitive_pr_53") or {}
    rust = (result.get("submitted") or {}).get("rustchain_2259") or {}
    total = ((result.get("settlement") or {}).get("rustchain_total_rtc"))
    lines = [
        "## Cloud decision",
        f"- VERIFIED: RustChain visible total is {total} RTC.",
        f"- VERIFIED: Cognitive-OS PR #53 state is {cognitive.get('state','unknown')}; merged={cognitive.get('merged','unknown')}.",
        f"- VERIFIED: RustChain #2259 state is {rust.get('state','unknown')}.",
    ]
    if opps:
        top = opps[0]
        lines += [
            f"- UNVERIFIED: Highest-scoring newly discovered opportunity is {top.get('title')} with parsed headline amount {top.get('amount_guess')}; it requires issuer/assignment/payment verification before work.",
            "- NEXT: Verify issuer legitimacy, current unassigned status, acceptance criteria and payout rail for the top candidate.",
        ]
    lines += [
        "- NEXT: Keep submitted claims/PRs in monitoring lane; do not idle on reviewer delay.",
        "- NEXT: Move immediately to the next independently funded lane when a candidate is assigned, stale, unfunded or unverifiable.",
        "- PAID GATE: Count money only after authoritative external settlement or payer-confirmed withdrawal-ready evidence.",
    ]
    return "\n".join(lines)

def call_openai(api_key):
    prompt = """You are the cloud revenue command brain. Use only the supplied evidence. Goal: maximize legitimate externally funded settlement while minimizing zero-revenue stretches. Never count claims, bids, PRs, listings, self-transfers, 402s, or headline rewards as revenue. No trading, gambling, deposits/stakes, fake traffic, spam, identity rental, or unauthorized exploitation.

Return: closest-to-cash verified lane; highest expected-value opportunity worth deeper verification; next three actions; what to park/reject; exact evidence required before calling anything paid. Label claims VERIFIED, INFERENCE, or UNVERIFIED. Be concise.

LIVE EVIDENCE:
""" + json.dumps(result, indent=2)
    payload = {
        "model":"gpt-5-mini",
        "messages":[
            {"role":"system","content":"Evidence first. Be economically rigorous and concise."},
            {"role":"user","content":prompt}
        ],
        "max_completion_tokens":900
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json","Authorization":"Bearer "+api_key},
        method="POST"
    )
    with urllib.request.urlopen(req,timeout=60) as r:
        data=json.loads(r.read().decode())
    return data["choices"][0]["message"]["content"]

key=os.getenv("OPENAI_API_KEY","").strip()
if key:
    try:
        text=call_openai(key)
    except Exception as e:
        text=deterministic()+"\n\nAI fallback reason: "+repr(e)
else:
    text=deterministic()+"\n\nAI provider: deterministic fallback (no cloud LLM credential configured)."

(root/"plan.md").write_text(text)
print(text)
