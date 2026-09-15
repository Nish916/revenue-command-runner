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
    floor=result.get("payment_floor") or {}\n    catalog=result.get("exploration_catalog") or {}

    lines=[
      "## NO-ZERO-HOUR PAYMENT CONTROLLER",
      f"- MODE: {floor.get('mode','ZERO_HOUR_EMERGENCY')}",
      f"- TARGET: {floor.get('target','Maximize probability of at least one legitimate external settlement per hour; never guarantee it.')}",
      f"- VERIFIED: RustChain visible total is {settle.get('rustchain_total_rtc')} RTC.",
      f"- VERIFIED: Cognitive-OS PR #53 state is {(sub.get('cognitive_pr_53') or {}).get('state','unknown')}.",
      f"- VERIFIED: RustChain #2259 state is {(sub.get('rustchain_2259') or {}).get('state','unknown')}.",
    ]

    if fast:
      x=fast[0]
      lines.append(f"- NOW: Closest-to-cash candidate [{x.get('source')}] {x.get('title')} — parsed amount {x.get('amount_guess')} — action {x.get('action')}.")
    elif intent:
      x=intent[0]
      lines.append(f"- NOW: Fresh buyer-intent [{x.get('source')}] {x.get('title')} — parsed amount {x.get('amount_guess')} — action {x.get('action')}. Verify the payer and scope before outreach.")
    else:
      lines.append("- NOW: No fast-cash or explicit buyer-intent candidate passed filters; immediately widen discovery instead of waiting on pending work.")

    if intent:
      x=intent[0]
      lines.append(f"- INTENT BEACON: [{x.get('source')}] {x.get('title')} — freshness/fit scored, action {x.get('action')}.")

    if contracts:
      lines.append(f"- CONTRACT POOL: {len(contracts)} ranked remote/contract jobs are available as a lower-speed independent payer lane.")

    lines.append(f"- EXPLORATION CATALOG: {catalog.get('total_sources',0)} tracked earning surfaces across modes {catalog.get('mode_counts',{})}.")

    if high:
      x=high[0]
      lines.append(f"- UPSIDE: [{x.get('source')}] {x.get('title')} — parsed budget/reward {x.get('amount_guess')} — action {x.get('action')}. Do not let this block fast-cash work.")

    ok=[s["source"] for s in src if s.get("ok")]
    bad=[s["source"] for s in src if not s.get("ok")]
    lines.append(f"- SOURCE HEALTH: OK={','.join(ok) or 'none'}; failed={','.join(bad) or 'none'}.")

    lines += [
      "- EXECUTION LAW 1: A pending proposal, PR, claim, review, KYC review or unpaid deliverable never satisfies the hourly floor.",
      "- EXECUTION LAW 2: If no settlement is verified, prioritize in this order: ACCEPTED/FUNDED work > paid qualification/task > prepaid fixed-scope service > warm buyer invoice/milestone > new verified bounty > high-ticket proposal.",
      "- EXECUTION LAW 3: Spend no more than 25% of a cycle on high-ticket research until a recurring cash floor exists.",
      "- EXECUTION LAW 4: Never spend two consecutive cycles on the same blocked payer/source without new evidence. PARK and rotate.",
      "- EXECUTION LAW 5: Maintain at least 5 independent payer lanes. If fewer than 5 survive filters, discovery expansion becomes the first action.",
      "- EXECUTION LAW 6: For direct client work, ask for upfront payment or funded milestone before substantial delivery.",
      "- EXECUTION LAW 7: Every cycle must produce NOW / NEXT / PARK. NOW must be a concrete action tied to a payer, not 'monitor'.",
      "- NEXT: Push the best authenticated APPLY/WORK lane; if authentication is unavailable, prepare exact submission/deliverable and rotate to another executable lane.",
      "- PARK: Any lane requiring deposit/stake, self-payment, fake demand, spam, identity rental, private-contact scraping, gambling/trading, or unauthorized exploitation.",
      "- PAID GATE: Only authoritative external settlement or payer-confirmed withdrawal-ready funds count as earnings.",
    ]
    return "\n".join(lines)

def call_openai(api_key):
    prompt="""You are the NO-ZERO-HOUR PAYMENT CONTROLLER for an India-based operator.

MISSION:
Maximize the probability of at least one legitimate externally funded settlement every hour. This is a target, not a guarantee. The long-term upside target is large, but until a recurring cash floor exists, do NOT let high-ticket research consume the cycle.

STRICT PRIORITY ORDER WHEN THE CURRENT HOUR HAS NO VERIFIED SETTLEMENT:
1. Already ACCEPTED/FUNDED work that can be completed now.
2. Paid qualification, hourly work, usability/evaluation/data task with a real payer.
3. Prepaid fixed-scope service that can be invoiced now.
4. Warm buyer that can be moved to upfront payment or a funded milestone.
5. Verified unassigned bounty with objective acceptance criteria and funded payout.
6. High-ticket RFP/proposal work.

OPERATING RULES:
- Pending proposal, PR, claim, review, KYC review, listing, headline reward, 402, self-transfer, or unpaid deliverable = ZERO earned.
- Never wait on one payer. If blocked, PARK immediately and rotate.
- Never spend two consecutive cycles on the same blocked source without new evidence.
- Maintain at least 5 independent payer classes and continuously expand buyer-intent/source beacons.
- High-ticket research gets max 25% of attention until a recurring floor exists.
- Every cycle must output NOW / NEXT / PARK.
- NOW must identify a concrete payer, exact work, expected payout, and first action. Never say merely "monitor".
- For direct-client work prefer upfront payment or funded milestone before substantial delivery.
- Count money only after authoritative external settlement or payer-confirmed withdrawal-ready evidence.
- No trading/speculation, gambling, self-funding, deposits/stakes to earn, fake buyers/traffic, spam, identity rental, private-contact scraping, account sales, or unauthorized security testing.
- Never fabricate buyer interest, acceptance, balance, or payment.

OUTPUT:
A) HOURLY FLOOR STATUS
B) NOW — one concrete closest-to-cash action
C) NEXT — two independent payer actions
D) UPSIDE — one high-ticket action
E) PARK — blocked/rejected lanes
F) PAID EVIDENCE REQUIRED

Label each material claim VERIFIED, INFERENCE, or UNVERIFIED.

LIVE EVIDENCE:
"""+json.dumps(result,indent=2)[:32000]

    payload={
      "model":"gpt-5-mini",
      "messages":[
        {"role":"system","content":"Payment-first. Evidence-first. Never confuse opportunity value with earnings."},
        {"role":"user","content":prompt}
      ],
      "max_completion_tokens":1100
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
  text=deterministic()+"\n\nAI provider: deterministic payment-first fallback."

(root/"plan.md").write_text(text)
print(text)
