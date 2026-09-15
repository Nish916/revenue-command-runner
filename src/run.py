#!/usr/bin/env python3
import json, re, urllib.request, urllib.parse, datetime

UA={"User-Agent":"revenue-command-runner/1.0"}

def get(url, timeout=20):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

def safe(fn):
    try:return fn()
    except Exception as e:return {"error":repr(e)}

def rust(miner):
    return safe(lambda:get("https://rustchain.org/wallet/balance?"+urllib.parse.urlencode({"miner_id":miner})))

def pr(repo,num):
    d=safe(lambda:get(f"https://api.github.com/repos/{repo}/pulls/{num}"))
    if "error" in d:return d
    return {"state":d.get("state"),"merged":d.get("merged"),"updated_at":d.get("updated_at"),"url":d.get("html_url")}

def issue(repo,num):
    d=safe(lambda:get(f"https://api.github.com/repos/{repo}/issues/{num}"))
    if "error" in d:return d
    return {"state":d.get("state"),"updated_at":d.get("updated_at"),"url":d.get("html_url"),"comments":d.get("comments")}

def search():
    qs=[
      'is:issue is:open label:bounty updated:>=2026-09-01',
      'is:issue is:open "USDC" bounty updated:>=2026-09-01',
      'is:issue is:open "$1000" bounty updated:>=2026-09-01',
      'is:issue is:open "$500" bounty updated:>=2026-09-01'
    ]
    out={}
    for q in qs:
        d=safe(lambda:get("https://api.github.com/search/issues?"+urllib.parse.urlencode({"q":q,"per_page":30,"sort":"updated","order":"desc"})))
        for it in d.get("items",[]) if isinstance(d,dict) else []:
            url=it.get("html_url") or ""
            repo_url=it.get("repository_url") or ""
            if "Nish916/revenue-command-runner" in url or "Nish916/revenue-command-runner" in repo_url:
                continue
            if it.get("assignees"):
                continue
            if re.search(r'(?i)(bounty-plaza|/arbitr/|bounty[-_]?radar|claim[-_]?tracker)', url):
                continue
            txt=(it.get("title") or "")+" "+(it.get("body") or "")
            if re.search(r'(?i)(casino|gambl|deposit.*to earn|stake.*to earn|flash usdt|captcha bypass|identity rental|account sale|due for payment)',txt):continue
            vals=[]
            for m in re.finditer(r'(?i)(?:\$|USD\s*|USDC\s*)([0-9][0-9,]*(?:\.\d+)?)',txt):
                try:vals.append(float(m.group(1).replace(",","")))
                except:pass
            amt=max(vals) if vals else 0
            if not (50 <= amt <= 100000):continue
            c=int(it.get("comments",0) or 0)
            score=amt/(1+0.2*c)
            out[it["html_url"]]={"title":it.get("title"),"url":it["html_url"],"amount_guess":amt,"comments":c,"score":round(score,2),"updated_at":it.get("updated_at")}
    return sorted(out.values(),key=lambda x:x["score"],reverse=True)[:20]

native=rust("RTCbc589ef246bc1c5c8c44117f1d66b226f33b9f73")
hosted=rust("Nish916")
result={
 "ts":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "settlement":{
   "rustchain_native":native,
   "rustchain_hosted":hosted,
   "rustchain_total_rtc":float(native.get("amount_rtc",0) or 0)+float(hosted.get("amount_rtc",0) or 0)
 },
 "submitted":{
   "cognitive_pr_53":pr("aLexzzz430/Cognitive-OS",53),
   "rustchain_2259":issue("Scottcjn/rustchain-bounties",2259)
 },
 "opportunities":search(),
 "rule":"Only authoritative external settlement counts as revenue."
}
print(json.dumps(result,indent=2))
