#!/usr/bin/env python3
import json, os, pathlib, urllib.request

root=pathlib.Path(__file__).resolve().parents[1]
result=json.loads((root/"result.json").read_text())

def deterministic():
    q=result.get("queue") or {}
    first=q.get("first_cash") or []
    apps=q.get("application_pipeline") or []
    fast=q.get("fast_cash") or []
    freelance=q.get("freelance_pipeline") or []
    high=q.get("high_ticket") or []
    intent=q.get("buyer_intent") or []
    contracts=q.get("contract_jobs") or []
    allq=q.get("all_ranked") or []
    sub=result.get("submitted") or {}
    settle=result.get("settlement") or {}
    src=result.get("source_status") or []
    floor=result.get("payment_floor") or {}
    catalog=result.get("exploration_catalog") or {}

    lines=[
      "## SUPER INFINITY AGGRESSIVE REVENUE CONTROLLER",
      "- ROLE: Cloud discovery is advisory only; authenticated mutations run in the local executor.",
      f"- MODE: {floor.get('mode','SUPER_INFINITY_AGGRESSIVE')}",
      f"- TARGET: {floor.get('target','Maximize legitimate externally funded settlement velocity with payer-first execution; never guarantee income.')}",
      f"- VERIFIED: RustChain visible total is {settle.get('rustchain_total_rtc')} RTC.",
      f"- VERIFIED: Cognitive-OS PR #53 state is {(sub.get('cognitive_pr_53') or {}).get('state','unknown')}.",
      f"- VERIFIED: RustChain #2259 state is {(sub.get('rustchain_2259') or {}).get('state','unknown')}.",
    ]

    if first:
      x=first[0]
      lines.append(f"- NOW: Cash-near funded/executable lane [{x.get('source')}] {x.get('title')} — amount {x.get('amount_guess')} {x.get('currency') or ''} — action {x.get('action')}.")
    else:
      lines.append("- NOW: No cloud-discovered opportunity qualifies as cash-near. Do not confuse screening-required roles, freelance listings, or buyer-intent signals with earnings; local authenticated executor owns real APPLY/CLAIM/START_WORK actions.")
    if freelance:
      x=freelance[0]
      lines.append(f"- DISCOVERY ONLY — FREELANCE: [{x.get('source')}] {x.get('title')} — parsed budget {x.get('amount_guess')}; application/bid not yet executed.")
    if apps:
      x=apps[0]
      lines.append(f"- APPLICATION PIPELINE (NOT CASH-NEAR): [{x.get('source')}] {x.get('title')} — published floor/reference {x.get('amount_guess')} {x.get('currency') or ''}; screening/application required.")

    if intent:
      x=intent[0]
      lines.append(f"- DISCOVERY ONLY — INTENT BEACON: [{x.get('source')}] {x.get('title')} — freshness/fit scored; payer/contact still unverified.")

    if contracts:
      lines.append(f"- CONTRACT POOL: {len(contracts)} ranked remote/contract jobs are available as a lower-speed independent payer lane.")

    lines.append(f"- EXPLORATION CATALOG: {catalog.get('total_sources',0)} tracked earning surfaces across modes {catalog.get('mode_counts',{})}.")

    if high:
      x=high[0]
      lines.append(f"- UPSIDE: [{x.get('source')}] {x.get('title')} — parsed budget/reward {x.get('amount_guess')} — action {x.get('action')}. Do not let this block fast-cash work.")

    ok=[s["source"] for s in src if s.get("ok")]
    bad=[s["source"] for s in src if not s.get("ok")]
    lines.append(f"- SOURCE HEALTH: OK={','.join(ok) or 'none'}; failed={','.join(bad) or 'none'}.")
    cat=result.get("exploration_catalog") or {}
    modes=cat.get("mode_counts") or {}
    total=int(cat.get("total_sources") or 0)
    auth=int(modes.get("AUTH_REQUIRED") or 0)
    if total:
      lines.append(f"- BOTTLENECK: {auth}/{total} tracked surfaces require authentication/manual account access; do not treat them as executable until an authorized session exists.")
    if first:
      lines.append("- BOTTLENECK: first-cash listings still require payer screening/application acceptance; discovery alone cannot create settlement.")

    lines += [
      "- GUARANTEE GATE: Never call an opportunity guaranteed before payer acceptance/allocation. Once fixed-pay funded work is accepted and completion criteria are under our control, it outranks every search lane.",
      "- EXECUTION LAW 1: A pending proposal, PR, claim, review, KYC review or unpaid deliverable never satisfies the hourly floor.",
      "- EXECUTION LAW 2: If no settlement is verified, prioritize in this order: ACCEPTED/FUNDED work > paid qualification/task > prepaid fixed-scope service > warm buyer invoice/milestone > new verified bounty > high-ticket proposal.",
      "- EXECUTION LAW 3: Spend no more than 10% of a cycle on high-ticket research until a recurring cash floor exists.",
      "- EXECUTION LAW 4: Never spend two consecutive cycles on the same blocked payer/source without new evidence. PARK and rotate.",
      "- EXECUTION LAW 5: Maintain at least 8 independent payer lanes. If fewer than 8 survive filters, discovery expansion becomes the first action.",
      "- EXECUTION LAW 6: For direct client work, ask for upfront payment or funded milestone before substantial delivery.",
      "- EXECUTION LAW 7: Every cycle must produce NOW / NEXT / PARK. NOW must be a concrete action tied to a payer, not 'monitor'.",
      "- NEXT: Push the best authenticated APPLY/WORK lane; if authentication is unavailable, prepare exact submission/deliverable and rotate to another executable lane.",
      "- PARK: Any lane requiring deposit/stake, self-payment, fake demand, spam, identity rental, private-contact scraping, gambling/trading, or unauthorized exploitation.",
      "- PAID GATE: Only authoritative external settlement or payer-confirmed withdrawal-ready funds count as earnings.",
    ]
    return "\n".join(lines)

def call_openai(api_key):
    prompt="""You are the SUPER_INFINITY_AGGRESSIVE REVENUE CONTROLLER for an India-based operator.

MISSION:
Run SUPER_INFINITY_AGGRESSIVE payer-first execution. Maximize legitimate externally funded settlement velocity. This is a target, never a guarantee. Do NOT let research, monitoring, or high-ticket speculation consume the cycle while executable paid work exists.

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
- Maintain at least 8 independent payer classes and continuously expand buyer-intent/source beacons.
- High-ticket research gets max 10% of attention until a recurring floor exists.
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
