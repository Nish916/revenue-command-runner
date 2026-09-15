#!/usr/bin/env python3
import concurrent.futures, datetime, html, json, os, re, urllib.parse, urllib.request

TOKEN=os.getenv("GITHUB_TOKEN","")
HEADERS={"User-Agent":"revenue-command-runner/2.0","Accept":"application/json,text/html;q=0.9,*/*;q=0.8"}
if TOKEN:
    HEADERS["Authorization"]="Bearer "+TOKEN

BAD=re.compile(r"(?i)(casino|gambl|deposit.*to earn|stake.*to earn|flash usdt|captcha bypass|identity rental|account sale|buy account|developer account verification|account verification|bulk sms|survey respondents|email leads|lead list|scrape private|private contacts|sniper bot|wash trade|self[- ]fund)")
FIT=re.compile(r"(?i)(python|javascript|typescript|api|integration|automation|ai|agent|research|technical writing|documentation|data|analytics|seo|marketing|growth|crm|salesforce|hubspot|qa|testing|web|node|content)")
MONEY=re.compile(r"(?i)(?:\$|USD\s*|USDC\s*|USDG\s*)([0-9][0-9,]*(?:\.\d+)?)")

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

def fetch(url,timeout=25):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8","ignore")

def get_json(url,timeout=25):
    return json.loads(fetch(url,timeout))

def safe(name,fn):
    try:
        items=fn()
        return {"source":name,"ok":True,"count":len(items),"items":items}
    except Exception as e:
        return {"source":name,"ok":False,"count":0,"error":repr(e),"items":[]}

def amount_guess(text):
    vals=[]
    for m in MONEY.finditer(text or ""):
        try: vals.append(float(m.group(1).replace(",","")))
        except: pass
    return max(vals) if vals else 0.0

def fit_score(text):
    return len(set(m.group(0).lower() for m in FIT.finditer(text or "")))

def clean_text(s):
    s=re.sub(r"<script.*?</script>"," ",s,flags=re.I|re.S)
    s=re.sub(r"<style.*?</style>"," ",s,flags=re.I|re.S)
    s=re.sub(r"<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",html.unescape(s)).strip()

def rust(miner):
    q=urllib.parse.urlencode({"miner_id":miner})
    try:return get_json("https://rustchain.org/wallet/balance?"+q)
    except Exception as e:return {"miner_id":miner,"error":repr(e)}

def gh_api(path,params=None):
    url="https://api.github.com"+path
    if params:url+="?"+urllib.parse.urlencode(params)
    return get_json(url)

def pr(repo,num):
    try:
        d=gh_api(f"/repos/{repo}/pulls/{num}")
        return {"state":d.get("state"),"merged":d.get("merged"),"updated_at":d.get("updated_at"),"url":d.get("html_url")}
    except Exception as e:return {"error":repr(e)}

def issue(repo,num):
    try:
        d=gh_api(f"/repos/{repo}/issues/{num}")
        return {"state":d.get("state"),"updated_at":d.get("updated_at"),"url":d.get("html_url"),"comments":d.get("comments")}
    except Exception as e:return {"error":repr(e)}

def github_paid():
    qs=[
      'is:issue is:open label:bounty updated:>=2026-09-01',
      'is:issue is:open in:title bounty updated:>=2026-09-01',
      'is:issue is:open "USDC" updated:>=2026-09-01',
      'is:issue is:open "$1000" updated:>=2026-09-01',
      'is:issue is:open "$500" updated:>=2026-09-01'
    ]
    raw={}
    for q in qs:
        d=gh_api("/search/issues",{"q":q,"per_page":50,"sort":"updated","order":"desc"})
        for it in d.get("items",[]): raw[it.get("html_url")]=it
    candidates=[]
    for url,it in raw.items():
        if not url:continue
        repo_url=it.get("repository_url") or ""
        if "Nish916/revenue-command-runner" in url or "Nish916/revenue-command-runner" in repo_url:continue
        if it.get("assignees"):continue
        if re.search(r"(?i)(bounty-plaza|/arbitr/|bounty[-_]?radar|claim[-_]?tracker)",url):continue
        txt=(it.get("title") or "")+" "+(it.get("body") or "")
        if BAD.search(txt) or re.search(r"(?i)due for payment",txt):continue
        amt=amount_guess(txt)
        if not (50 <= amt <= 100000):continue
        comments=int(it.get("comments",0) or 0)
        repo=repo_url.rsplit("/",2)[-2]+"/"+repo_url.rsplit("/",1)[-1] if "/repos/" in repo_url else ""
        candidates.append({
          "source":"github","kind":"bounty","title":it.get("title"),"url":url,
          "amount_guess":amt,"comments":comments,"fit":fit_score(txt),
          "updated_at":it.get("updated_at"),"repo":repo
        })
    # Trust-check only strongest 18.
    candidates=sorted(candidates,key=lambda x:(x["amount_guess"],x["fit"]),reverse=True)[:18]
    out=[]
    for x in candidates:
        stars=forks=0
        try:
            meta=gh_api("/repos/"+x["repo"])
            stars=int(meta.get("stargazers_count",0) or 0); forks=int(meta.get("forks_count",0) or 0)
        except: pass
        trust=1+(1 if stars>=5 else 0)+(1 if forks>=2 else 0)+(1 if x["comments"]>=1 else 0)
        if trust<2:continue
        x["trust"]=trust;x["stars"]=stars;x["forks"]=forks
        x["score"]=round(x["amount_guess"]*(1+0.08*x["fit"])*(0.7+0.1*trust)/(1+0.18*x["comments"]),2)
        x["action"]="VERIFY"
        out.append(x)
    return sorted(out,key=lambda x:x["score"],reverse=True)

def laborx():
    s=fetch("https://laborx.com/jobs")
    blocks=re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',s,re.I|re.S)
    out=[]
    for b in blocks:
        try:d=json.loads(html.unescape(b))
        except:continue
        for x in (d if isinstance(d,list) else [d]):
            if not isinstance(x,dict) or x.get("@type")!="JobPosting":continue
            title=x.get("title") or ""
            desc=clean_text(x.get("description") or "")
            txt=title+" "+desc
            if BAD.search(txt):continue
            loc=x.get("applicantLocationRequirements") or []
            countries=[z.get("name","") for z in loc if isinstance(z,dict)]
            if countries and "India" not in countries:continue
            salary=x.get("estimatedSalary") or {}
            val=(salary.get("value") or {}) if isinstance(salary,dict) else {}
            raw_amt=val.get("value")
            try:amt=float(raw_amt) if raw_amt is not None else amount_guess(txt)
            except:amt=amount_guess(txt)
            if amt<=0:continue
            low=txt.lower()
            geo_exclude=["italy only","uk only","united kingdom only","in the uk","uk welcome","brazil only","brasil real","us only","u.s. only","need us man","united states only","senegal","togo","benin","portugal company formation"]
            if any(g in low for g in geo_exclude): continue
            unit=val.get("unitText") or ""
            fit=fit_score(txt)
            score=amt*(1+0.1*fit)
            out.append({
              "source":"laborx","kind":"freelance","title":title,
              "url":x.get("url") or "https://laborx.com/jobs","amount_guess":amt,
              "currency":salary.get("currency") if isinstance(salary,dict) else None,
              "unit":unit,"fit":fit,"score":round(score,2),
              "date_posted":x.get("datePosted"),"action":"APPLY"
            })
    return sorted(out,key=lambda x:x["score"],reverse=True)[:20]

def oneforma():
    s=fetch("https://www.oneforma.com/jobs/")
    out=[]
    # Job titles and nearby cards. Rates are often exposed in text/structured payload.
    for m in re.finditer(r'<h[23][^>]*>(.*?)</h[23]>',s,re.I|re.S):
        title=clean_text(m.group(1))
        if len(title)<4:continue
        frag=s[m.start():m.start()+7000]
        text=clean_text(frag)
        if "India" not in text and "Remote" not in text:continue
        amt=amount_guess(text)
        if amt<=0:continue
        fit=fit_score(title+" "+text[:1500])
        href=""
        hm=re.search(r'href=["\']([^"\']+)["\']',frag,re.I)
        if hm: href=urllib.parse.urljoin("https://www.oneforma.com/jobs/",hm.group(1))
        out.append({
          "source":"oneforma","kind":"paid-hourly","title":title[:180],
          "url":href or "https://www.oneforma.com/jobs/","amount_guess":amt,
          "fit":fit,"score":round(amt*50*(1+0.08*fit),2),"action":"APPLY"
        })
    # De-dupe.
    seen={x["title"]:x for x in out}
    return sorted(seen.values(),key=lambda x:x["score"],reverse=True)[:20]

def superteam():
    s=fetch("https://superteam.fun/earn/bounties/")
    text=clean_text(s)
    out=[]
    # Capture nearby chunks around currency mentions. This is discovery only.
    for m in re.finditer(r'(?i)([0-9][0-9,]*(?:\.\d+)?)\s*(USDC|USDG|USD)',text):
        try:amt=float(m.group(1).replace(",",""))
        except:continue
        if not (50<=amt<=100000):continue
        chunk=text[max(0,m.start()-220):m.start()+420]
        if BAD.search(chunk):continue
        fit=fit_score(chunk)
        out.append({
          "source":"superteam","kind":"bounty","title":chunk[:220],
          "url":"https://superteam.fun/earn/bounties/","amount_guess":amt,
          "fit":fit,"score":round(amt*(1+0.08*fit),2),"action":"VERIFY"
        })
    # de-dupe by amount+title
    uniq={}
    for x in out:uniq[(x["amount_guess"],x["title"])]=x
    return sorted(uniq.values(),key=lambda x:x["score"],reverse=True)[:15]

def inspect_rfp_detail(url):
    try:
        page=fetch(url)
        text=clean_text(page)
        req=""
        m=re.search(r'KEY REQUIREMENTS(.*?)(?:BUDGET|CONTRACT DURATION|TIMELINE)',text,re.I|re.S)
        if m: req=m.group(1).strip()[:3500]
        hard=[]
        patterns=[
          r'must be registered with[^.]{0,180}',r'must be licensed[^.]{0,180}',
          r'must be located[^.]{0,180}',r'must have (?:an? )?(?:office|physical presence)[^.]{0,180}',
          r'local vendor[^.]{0,180}',r'ability to travel[^.]{0,180}',
          r'must have experience in[^.]{0,220}'
        ]
        for pat in patterns:
            for mm in re.finditer(pat,req,re.I): hard.append(mm.group(0).strip())
        restricted=any(re.search(r'(?i)(must be registered with|must be located|must have (?:an? )?(?:office|physical presence)|local vendor)',h) for h in hard)
        gap=any(re.search(r'(?i)must have experience in',h) for h in hard)
        return {"requirements":req[:1800],"hard_flags":hard[:8],"restricted":restricted,"requirement_gap":gap}
    except Exception as e:
        return {"detail_error":repr(e),"restricted":False,"requirement_gap":False,"hard_flags":[]}

def settle_rfps():
    urls=[
      "https://usesettle.com/rfp-hunter/categories/marketing-advertising-and-social-media",
      "https://usesettle.com/rfp-hunter/categories/marketing-strategy-and-branding"
    ]
    out=[]
    for base in urls:
        s=fetch(base)
        for m in re.finditer(r'<a[^>]+href=["\'](/rfp-hunter/[^"\']+)["\'][^>]*>(.*?)</a>',s,re.I|re.S):
            href=m.group(1); card=m.group(2)
            title_m=re.search(r'<h3[^>]*>(.*?)</h3>',card,re.I|re.S)
            if not title_m: continue
            title=clean_text(title_m.group(1))
            desc_m=re.search(r'<p[^>]*>(.*?)</p>',card,re.I|re.S)
            desc=clean_text(desc_m.group(1)) if desc_m else ""
            pairs={clean_text(a).rstrip(':'):clean_text(b) for a,b in re.findall(r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>',card,re.I|re.S)}
            budget_text=pairs.get('Budget','')
            amt=amount_guess(budget_text)
            if not (1000<=amt<=500000): continue
            deadline=pairs.get('Deadline','')
            issuer=pairs.get('Issuer','')
            location=pairs.get('Location','')
            txt=' '.join([title,desc,issuer,location])
            if BAD.search(txt): continue
            fit=fit_score(txt)
            out.append({
              "source":"rfp","kind":"consulting-rfp","title":title,
              "url":urllib.parse.urljoin(base,href),"amount_guess":amt,
              "issuer":issuer,"deadline":deadline,"location":location,
              "description":desc[:500],"fit":fit,
              "score":round(amt*(1+0.12*fit)*0.45,2),"action":"VERIFY"
            })
    uniq={x["url"]:x for x in out}
    ranked=sorted(uniq.values(),key=lambda x:x["score"],reverse=True)[:18]
    for x in ranked:
        detail=inspect_rfp_detail(x["url"])
        x["hard_flags"]=detail.get("hard_flags",[])
        x["requirements"]=detail.get("requirements","")
        if detail.get("restricted"):
            x["action"]="PARK"
            x["eligibility"]="RESTRICTED_OR_LOCAL_REGISTRATION"
            x["score"]=round(x["score"]*0.05,2)
        elif detail.get("requirement_gap"):
            x["action"]="VERIFY_GAP"
            x["eligibility"]="REQUIREMENT_GAP"
            x["score"]=round(x["score"]*0.25,2)
        else:
            x["eligibility"]="POSSIBLE_UNVERIFIED"
    return sorted(ranked,key=lambda x:x["score"],reverse=True)

def devpost():
    s=fetch("https://devpost.com/hackathons")
    txt=clean_text(s)
    out=[]
    for m in MONEY.finditer(txt):
        try:amt=float(m.group(1).replace(",",""))
        except:continue
        if not (1000<=amt<=1000000):continue
        chunk=txt[max(0,m.start()-250):m.start()+500]
        if BAD.search(chunk):continue
        fit=fit_score(chunk)
        out.append({
          "source":"devpost","kind":"challenge","title":chunk[:240],
          "url":"https://devpost.com/hackathons","amount_guess":amt,"fit":fit,
          "score":round(amt*(1+0.08*fit)*0.20,2),"action":"VERIFY"
        })
    uniq={}
    for x in out:uniq[(x["amount_guess"],x["title"])]=x
    return sorted(uniq.values(),key=lambda x:x["score"],reverse=True)[:12]

def security_programs():
    s=fetch("https://bountyhunte.rs/programs")
    txt=clean_text(s)
    out=[]
    for m in MONEY.finditer(txt):
        try:amt=float(m.group(1).replace(",",""))
        except:continue
        if not (1000<=amt<=1000000):continue
        chunk=txt[max(0,m.start()-180):m.start()+360]
        out.append({
          "source":"security","kind":"authorized-bug-bounty","title":chunk[:220],
          "url":"https://bountyhunte.rs/programs","amount_guess":amt,"fit":1,
          "score":round(amt*0.08,2),"action":"VERIFY_SCOPE"
        })
    uniq={}
    for x in out:uniq[(x["amount_guess"],x["title"])]=x
    return sorted(uniq.values(),key=lambda x:x["score"],reverse=True)[:10]

SOURCES=[
  ("github",github_paid),("laborx",laborx),("oneforma",oneforma),
  ("superteam",superteam),("rfp",settle_rfps),("devpost",devpost),
  ("security",security_programs)
]
with concurrent.futures.ThreadPoolExecutor(max_workers=len(SOURCES)) as ex:
    futs={ex.submit(safe,name,fn):name for name,fn in SOURCES}
    source_results=[f.result() for f in concurrent.futures.as_completed(futs)]

all_items=[]
for src in source_results: all_items.extend(src.get("items",[]))
all_items=sorted(all_items,key=lambda x:x.get("score",0),reverse=True)

native=rust("RTCbc589ef246bc1c5c8c44117f1d66b226f33b9f73")
hosted=rust("Nish916")
total=float(native.get("amount_rtc",0) or 0)+float(hosted.get("amount_rtc",0) or 0)

result={
 "ts":now(),
 "settlement":{
   "rustchain_native":native,"rustchain_hosted":hosted,"rustchain_total_rtc":total
 },
 "submitted":{
   "cognitive_pr_53":pr("aLexzzz430/Cognitive-OS",53),
   "rustchain_2259":issue("Scottcjn/rustchain-bounties",2259)
 },
 "source_status":[{k:v for k,v in s.items() if k!="items"} for s in sorted(source_results,key=lambda x:x["source"])],
 "queue":{
   "high_ticket":[x for x in all_items if x.get("amount_guess",0)>=2500][:12],
   "fast_cash":[x for x in all_items if x.get("kind") in ("paid-hourly","freelance")][:12],
   "all_ranked":all_items[:35]
 },
 "rules":{
   "count_as_revenue":["authoritative external settlement","payer-confirmed withdrawal-ready balance"],
   "do_not_count":["claim","bid","PR","listing","headline reward","self-transfer","402","unaccepted deliverable"],
   "blocked_lane_policy":"PARK_AND_CONTINUE"
 }
}
print(json.dumps(result,indent=2))
