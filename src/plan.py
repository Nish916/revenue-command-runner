#!/usr/bin/env python3
import json, os, pathlib, urllib.request

root=pathlib.Path(__file__).resolve().parents[1]
result=json.loads((root/"result.json").read_text())

def deterministic():
    q=result.get("queue") or {}
    fast=q.get("fast_cash") or []
    high=q.get("high_ticket") or []
    allq=q.get("all_ranked") or []
    sub=result.get("submitted") or {}
    settle=result.get("settlement") or {}
    src=result.get("source_status") or []

    lines=[
      "## Cloud decision",
      f"- VERIFIED: RustChain visible total is {settle.get('rustchain_total_rtc')} RTC.",
      f"- VERIFIED: Cognitive-OS PR #53 state is {(sub.get('cognitive_pr_53') or {}).get('state','unknown')}.",
      f"- VERIFIED: RustChain #2259 state is {(sub.get('rustchain_2259') or {}).get('state','unknown')}.",
    ]
    if fast:
      x=fast[0]
      lines.append(f"- INFERENCE: Closest-to-cash public lane is [{x.get('source')}] {x.get('title')} — parsed amount {x.get('amount_guess')} — action {x.get('action')}.")
    else:
      lines.append("- VERIFIED: No fast-cash public lane passed the current filters in this run.")
    if high:
      x=high[0]
      lines.append(f"- UNVERIFIED: Highest expected-value discovery is [{x.get('source')}] {x.get('title')} — parsed amount {x.get('amount_guess')}; issuer, assignment, eligibility and payout must be verified before work.")
    elif allq:
      x=allq[0]
      lines.append(f"- UNVERIFIED: Top discovered lane is [{x.get('source')}] {x.get('title')} — parsed amount {x.get('amount_guess')}.")
    ok=[s["source"] for s in src if s.get("ok")]
    bad=[s["source"] for s in src if not s.get("ok")]
    lines.append(f"- VERIFIED: Source health OK={','.join(ok) or 'none'}; failed={','.join(bad) or 'none'}.")
    lines += [
      "- NEXT 1: Verify top high-ticket candidate against its original issuer before any substantial work.",
      "- NEXT 2: Push the strongest fast-cash APPLY lane whenever an authenticated account/session is available.",
      "- NEXT 3: Keep submitted claims/PRs in monitoring; blocked lanes are PARKED, never allowed to idle the engine.",
      "- PAID GATE: Count money only after authoritative external settlement or payer-confirmed withdrawal-ready evidence.",
    ]
    return "\n".join(lines)

def call_openai(api_key):
    prompt="""You are the cloud revenue command brain. Use only supplied evidence. Goal: maximize legitimate externally funded settlement while minimizing zero-revenue stretches. Never count claims, bids, PRs, listings, self-transfers, 402s or headline rewards as revenue. No trading, gambling, deposits/stakes, fake traffic, spam, identity rental, or unauthorized exploitation.

Return: closest-to-cash verified lane; highest expected-value lane worth deeper verification; next 3 actions; what to park/reject; exact evidence needed before calling anything paid. Label each statement VERIFIED, INFERENCE, or UNVERIFIED. Be concise.

LIVE EVIDENCE:
"""+json.dumps(result,indent=2)[:30000]
    payload={
      "model":"gpt-5-mini",
      "messages":[
        {"role":"system","content":"Evidence first. Be economically rigorous and concise."},
        {"role":"user","content":prompt}
      ],
      "max_completion_tokens":900
    }
    req=urllib.request.Request(
      "https://api.openai.com/v1/chat/completions",
      data=json.dumps(payload).encode(),
      headers={"Content-Type":"application/json","Authorization":"Bearer "+api_key},
      method="POST"
    )
    with urllib.request.urlopen(req,timeout=60) as r:
      d=json.loads(r.read().decode())
    return d["choices"][0]["message"]["content"]

key=os.getenv("OPENAI_API_KEY","").strip()
if key:
  try:text=call_openai(key)
  except Exception as e:text=deterministic()+"\n\nAI fallback reason: "+repr(e)
else:
  text=deterministic()+"\n\nAI provider: deterministic fallback (no cloud LLM credential configured)."

(root/"plan.md").write_text(text)
print(text)
