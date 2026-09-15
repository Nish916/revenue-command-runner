#!/usr/bin/env python3
import datetime, json, pathlib, time, urllib.parse, urllib.request

root = pathlib.Path(__file__).resolve().parents[1]
base = json.loads((root / "result.json").read_text())
queue = base.get("queue") or {}
first = queue.get("first_cash") or []
fast = queue.get("fast_cash") or []
ranked = queue.get("all_ranked") or []

UA = {"User-Agent": "revenue-command-runner-minute/1.0"}

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def read_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def rust(miner):
    q = urllib.parse.urlencode({"miner_id": miner})
    try:
        return read_json("https://rustchain.org/wallet/balance?" + q)
    except Exception as e:
        return {"miner_id": miner, "error": repr(e)}

def settlement():
    native = rust("RTCbc589ef246bc1c5c8c44117f1d66b226f33b9f73")
    hosted = rust("Nish916")
    total = float(native.get("amount_rtc", 0) or 0) + float(hosted.get("amount_rtc", 0) or 0)
    return {"native": native, "hosted": hosted, "total_rtc": total}

def pick(cycle):
    pool = []
    seen = set()
    for item in first + fast + ranked:
        key = (item.get("source"), item.get("url"), item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        if item.get("action") == "PARK":
            continue
        pool.append(item)
    return pool[cycle % len(pool)] if pool else None

start = settlement()
cycles = []
for i in range(4):
    cur = settlement()
    delta = round(cur["total_rtc"] - start["total_rtc"], 8)
    item = pick(i)
    cycles.append({
        "cycle": i + 1,
        "ts": now(),
        "settlement_total_rtc": cur["total_rtc"],
        "settlement_delta_rtc": delta,
        "status": "SETTLED" if delta > 0 else "ZERO_SETTLEMENT",
        "now": {
            "source": item.get("source") if item else None,
            "kind": item.get("kind") if item else None,
            "title": item.get("title") if item else "DISCOVERY_EXPANSION",
            "url": item.get("url") if item else None,
            "amount_guess": item.get("amount_guess") if item else None,
            "action": item.get("action") if item else "EXPAND_DISCOVERY",
        },
        "rule": "No blocked or merely pending item can satisfy the payment floor.",
    })
    print(json.dumps(cycles[-1], ensure_ascii=False), flush=True)
    if i < 3:
        time.sleep(55)

out = {
    "started_at": cycles[0]["ts"],
    "ended_at": cycles[-1]["ts"],
    "start_settlement": start,
    "cycles": cycles,
    "final_delta_rtc": cycles[-1]["settlement_delta_rtc"],
    "minute_mode": "4 micro-cycles inside each scheduled cloud run",
}
(root / "minute_state.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
