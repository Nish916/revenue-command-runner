#!/usr/bin/env python3
import concurrent.futures, datetime, html, json, os, pathlib, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[1]
TOKEN=os.getenv("GITHUB_TOKEN","")
HEADERS={"User-Agent":"revenue-command-runner/2.0","Accept":"application/json,text/html;q=0.9,*/*;q=0.8"}
if TOKEN:
    HEADERS["Authorization"]="Bearer "+TOKEN

BAD=re.compile(r"(?i)(casino|gambl|deposit.*to earn|stake.*to earn|flash usdt|captcha bypass|identity rental|account sale|buy account|developer account verification|account verification|trial registration|register account|create account|sign up.*account|bulk sms|survey respondents|email leads|lead list|scrape private|private contacts|mychart|health record data sharing|medical records sharing|patient portal data sharing|sniper bot|wash trade|self[- ]fund)")
FIT=re.compile(r"(?i)(python|javascript|typescript|api|integration|automation|ai|agent|research|technical writing|documentation|data|analytics|seo|marketing|growth|crm|salesforce|hubspot|qa|testing|web|node|content)")
MONEY=re.compile(r"(?i)(?:\$|USD\s*|USDC\s*|USDG\s*)([0-9][0-9,]*(?:\.\d+)?)")
DEMAND=re.compile(r"(?i)(?:looking for|need|seeking|hiring|wanted|want to hire|contracting|paid)[^.\\n]{0,100}(?:consultant|freelancer|contractor|developer|engineer|marketer|marketing|crm|salesforce|hubspot|automation|ai|api|writer|analyst|researcher|help|work|task|bounty)")

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
        if BAD.search(title+" "+text): continue
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


def remoteok():
    data=get_json("https://remoteok.com/api")
    out=[]
    for x in data[1:] if isinstance(data,list) else []:
        if not isinstance(x,dict): continue
        title=x.get("position") or ""
        tags=" ".join(x.get("tags") or [])
        txt=" ".join([title,x.get("company") or "",tags,x.get("description") or ""])
        if BAD.search(txt) or fit_score(txt)==0: continue
        salary_max=float(x.get("salary_max") or 0)
        salary_min=float(x.get("salary_min") or 0)
        amt=salary_max or salary_min
        fit=fit_score(txt)
        out.append({"source":"remoteok","kind":"contract-job","title":title,
          "company":x.get("company"),"url":x.get("url") or x.get("apply_url") or "https://remoteok.com/",
          "amount_guess":amt,"amount_basis":"annual_salary_if_disclosed","fit":fit,
          "score":round((fit+1)*120 + min(amt,250000)*0.002,2),
          "date":x.get("date"),"action":"APPLY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:25]

def arbeitnow():
    data=get_json("https://www.arbeitnow.com/api/job-board-api")
    out=[]
    for x in data.get("data",[]):
        title=x.get("title") or ""
        desc=clean_text(x.get("description") or "")
        txt=title+" "+desc+" "+" ".join(x.get("tags") or [])
        if BAD.search(txt) or fit_score(txt)==0: continue
        remote=bool(x.get("remote"))
        fit=fit_score(txt)
        out.append({"source":"arbeitnow","kind":"contract-job","title":title,
          "company":x.get("company_name"),"url":x.get("url"),
          "amount_guess":amount_guess(txt),"fit":fit,"remote":remote,
          "score":round((fit+1)*90 + (50 if remote else 0),2),
          "created_at":x.get("created_at"),"action":"APPLY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:25]

def remotive():
    data=get_json("https://remotive.com/api/remote-jobs?limit=100")
    out=[]
    for x in data.get("jobs",[]):
        title=x.get("title") or ""
        desc=clean_text(x.get("description") or "")
        txt=title+" "+desc+" "+(x.get("candidate_required_location") or "")
        if BAD.search(txt) or fit_score(txt)==0: continue
        loc=(x.get("candidate_required_location") or "").lower()
        if loc and not any(k in loc for k in ["worldwide","anywhere","global","india","asia","apac"]): continue
        salary=x.get("salary") or ""
        fit=fit_score(txt)
        out.append({"source":"remotive","kind":"contract-job","title":title,
          "company":x.get("company_name"),"url":x.get("url"),
          "amount_guess":amount_guess(salary),"amount_text":salary,"fit":fit,
          "score":round((fit+1)*110 + amount_guess(salary)*0.01,2),
          "publication_date":x.get("publication_date"),"action":"APPLY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:25]

def freelancer():
    data=get_json("https://www.freelancer.com/api/projects/0.1/projects/active/?compact=true&limit=100")
    out=[]
    for x in (data.get("result") or {}).get("projects",[]):
        title=x.get("title") or ""
        desc=x.get("preview_description") or ""
        txt=title+" "+desc
        if BAD.search(txt): continue
        fit=fit_score(txt)
        if fit==0: continue
        budget=x.get("budget") or {}
        cur=x.get("currency") or {}
        mx=float(budget.get("maximum") or 0)
        mn=float(budget.get("minimum") or 0)
        rate=float(cur.get("exchange_rate") or 0)
        usd=(mx or mn)*rate if rate else 0
        bids=(x.get("bid_stats") or {}).get("bid_count") or 0
        score=usd*(1+0.12*fit)/(1+0.08*float(bids))
        out.append({"source":"freelancer","kind":"freelance","title":title,
          "url":"https://www.freelancer.com/projects/"+str(x.get("id")),
          "amount_guess":round(usd,2),"currency":cur.get("code"),"budget_native":budget,
          "fit":fit,"bids":bids,"score":round(score,2),"urgent":bool(x.get("urgent")),"action":"APPLY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:30]

def braintrust():
    data=get_json("https://app.usebraintrust.com/api/jobs")
    out=[]
    for x in data.get("results",[]):
        title=x.get("title") or ""
        skills=" ".join(z.get("name","") for z in (x.get("main_skills") or []) if isinstance(z,dict))
        txt=title+" "+skills
        if BAD.search(txt) or fit_score(txt)==0: continue
        try: lo=float(x.get("budget_minimum_usd") or 0)
        except: lo=0
        try: hi=float(x.get("budget_maximum_usd") or 0)
        except: hi=0
        rate=hi or lo
        fit=fit_score(txt)
        pay_type=str(x.get("payment_type") or "hourly").lower()
        kind="paid-hourly" if pay_type in ("hourly","hour","per_hour") else ("paid-task" if pay_type in ("per_task","task","fixed") else "contract-job")
        score_mult=12 if kind=="paid-hourly" else 8 if kind=="paid-task" else 0.02
        out.append({"source":"braintrust","kind":kind,"title":title,
          "company":((x.get("employer") or {}).get("name")),
          "url":"https://app.usebraintrust.com/jobs/"+str(x.get("id")),
          "amount_guess":rate,"amount_basis":pay_type,
          "fit":fit,"score":round(rate*score_mult*(1+0.25*fit),2),"action":"APPLY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:25]

def jobicy():
    data=get_json("https://jobicy.com/api/v2/remote-jobs?count=50")
    out=[]
    for x in data.get("jobs",[]):
        title=x.get("jobTitle") or ""
        desc=clean_text(x.get("jobDescription") or "")
        txt=title+" "+desc+" "+str(x.get("jobGeo") or "")
        if BAD.search(txt) or fit_score(txt)==0: continue
        geo=str(x.get("jobGeo") or "").lower()
        if geo and not any(k in geo for k in ["anywhere","worldwide","global","india","asia","apac"]): continue
        try: hi=float(x.get("annualSalaryMax") or 0)
        except: hi=0
        try: lo=float(x.get("annualSalaryMin") or 0)
        except: lo=0
        amt=hi or lo
        fit=fit_score(txt)
        out.append({"source":"jobicy","kind":"contract-job","title":title,
          "company":x.get("companyName"),"url":x.get("url"),
          "amount_guess":amt,"amount_basis":"annual_salary_if_disclosed","fit":fit,
          "score":round((fit+1)*100 + min(amt,250000)*0.002,2),
          "pubDate":x.get("pubDate"),"action":"APPLY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:25]

def wwr():
    xml=fetch("https://weworkremotely.com/remote-jobs.rss")
    root=ET.fromstring(xml)
    out=[]
    for item in root.findall(".//item"):
        title=item.findtext("title") or ""
        desc=clean_text(item.findtext("description") or "")
        txt=title+" "+desc
        if BAD.search(txt) or fit_score(txt)==0: continue
        region=item.findtext("region") or ""
        if region and "anywhere" not in region.lower() and "world" not in region.lower(): continue
        fit=fit_score(txt)
        out.append({"source":"wwr","kind":"contract-job","title":title,
          "url":item.findtext("link"),"amount_guess":amount_guess(txt),"fit":fit,
          "region":region,"score":round((fit+1)*95,2),
          "pubDate":item.findtext("pubDate"),"action":"APPLY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:25]

def himalayas():
    data=get_json("https://himalayas.app/jobs/api")
    out=[]
    for x in data.get("jobs",[]):
        title=x.get("title") or ""
        desc=x.get("description") or x.get("excerpt") or ""
        txt=title+" "+clean_text(desc)
        if BAD.search(txt) or fit_score(txt)==0: continue
        locs=" ".join(x.get("locationRestrictions") or []) if isinstance(x.get("locationRestrictions"),list) else str(x.get("locationRestrictions") or "")
        low=locs.lower()
        if low and not any(k in low for k in ["worldwide","anywhere","global","india","asia","apac"]): continue
        fit=fit_score(txt)
        try: hi=float(x.get("maxSalary") or 0)
        except: hi=0
        try: lo=float(x.get("minSalary") or 0)
        except: lo=0
        amt=hi or lo
        out.append({"source":"himalayas","kind":"contract-job","title":title,
          "company":x.get("companyName"),"url":x.get("applicationLink") or x.get("url"),
          "amount_guess":amt,"fit":fit,
          "score":round((fit+1)*100 + min(amt,250000)*0.002,2),
          "postedAt":x.get("publishedAt") or x.get("createdAt"),"action":"APPLY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:25]

def devpost_api():
    data=get_json("https://devpost.com/api/hackathons?status[]=open&order_by=deadline")
    out=[]
    for x in data.get("hackathons",[]):
        title=x.get("title") or ""
        themes=" ".join(z.get("name","") for z in (x.get("themes") or []) if isinstance(z,dict))
        txt=title+" "+themes
        prize_text=clean_text(x.get("prize_amount") or "")
        amt=amount_guess(prize_text)
        if amt<=0:
            nums=re.findall(r'[0-9][0-9,]*(?:\\.[0-9]+)?',prize_text)
            try: amt=max(float(n.replace(",","")) for n in nums) if nums else 0
            except: amt=0
        if amt<=0 or BAD.search(txt): continue
        fit=fit_score(txt)
        out.append({"source":"devpost","kind":"challenge","title":title,
          "url":x.get("url"),"amount_guess":amt,"fit":fit,
          "time_left":x.get("time_left_to_submission"),
          "score":round(amt*(0.15+0.03*fit),2),"action":"VERIFY"})
    return sorted(out,key=lambda x:x["score"],reverse=True)[:20]

def hn_intent():
    queries=["looking for consultant","need consultant","seeking contractor","looking for freelancer",
      "need hubspot","need salesforce","need crm","need automation","need marketer",
      "looking for marketing","need api integration","need ai automation","hiring contractor"]
    out={}
    now_i=int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    for q in queries:
        url="https://hn.algolia.com/api/v1/search_by_date?"+urllib.parse.urlencode({"query":q,"tags":"story","hitsPerPage":20})
        data=get_json(url)
        for h in data.get("hits",[]):
            created=int(h.get("created_at_i") or 0)
            age_h=(now_i-created)/3600 if created else 9999
            if age_h>336: continue
            title=h.get("title") or ""
            body=clean_text(h.get("story_text") or "")
            txt=title+" "+body
            fit=fit_score(txt)
            if fit==0 or BAD.search(txt) or not DEMAND.search(txt): continue
            amt=amount_guess(txt)
            obj=h.get("objectID")
            link=h.get("url") or ("https://news.ycombinator.com/item?id="+str(obj))
            score=(fit+1)*180/(1+age_h/36) + min(amt,10000)*0.05
            out[link]={"source":"hn-intent","kind":"buyer-intent","title":title or body[:180],
              "url":link,"amount_guess":amt,"fit":fit,"age_hours":round(age_h,1),
              "points":h.get("points"),"comments":h.get("num_comments"),
              "score":round(score,2),"action":"VERIFY_CONTACT"}
    return sorted(out.values(),key=lambda x:x["score"],reverse=True)[:30]

def github_intent():
    qs=['is:issue is:open "looking for consultant" updated:>=2026-09-01',
      'is:issue is:open "need consultant" updated:>=2026-09-01',
      'is:issue is:open "paid" "help wanted" updated:>=2026-09-01',
      'is:issue is:open "need help" automation updated:>=2026-09-01',
      'is:issue is:open "contractor" updated:>=2026-09-01']
    out={}
    for q in qs:
        d=gh_api("/search/issues",{"q":q,"per_page":30,"sort":"updated","order":"desc"})
        for it in d.get("items",[]):
            if it.get("assignees"): continue
            txt=(it.get("title") or "")+" "+(it.get("body") or "")
            fit=fit_score(txt)
            if fit==0 or BAD.search(txt) or not DEMAND.search(txt): continue
            url=it.get("html_url")
            amt=amount_guess(txt)
            comments=int(it.get("comments") or 0)
            score=(fit+1)*120 + min(amt,10000)*0.05 - min(comments,20)*2
            out[url]={"source":"github-intent","kind":"buyer-intent","title":it.get("title"),
              "url":url,"amount_guess":amt,"fit":fit,"comments":comments,
              "updated_at":it.get("updated_at"),"score":round(score,2),"action":"VERIFY_CONTACT"}
    return sorted(out.values(),key=lambda x:x["score"],reverse=True)[:30]


def nearskill():
    """Fresh published-pay remote roles/studies, filtered for India + Nishant-profile fit."""
    searches=["crm","hubspot","salesforce","revenue operations","marketing","growth","customer success","prompt engineering","ai evaluation"]
    browser_headers={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/149 Safari/537.36"}
    def grab(url):
        req=urllib.request.Request(url,headers=browser_headers)
        with urllib.request.urlopen(req,timeout=18) as r:
            return r.read().decode("utf-8","ignore")
    links=set()
    for q in searches:
        try:
            page=grab("https://nearskill.in/jobs?"+urllib.parse.urlencode({"search":q}))
            for href in re.findall(r'/jobs/[A-Za-z0-9_-]+',page):
                if href != "/jobs/category": links.add(urllib.parse.urljoin("https://nearskill.in",href))
        except Exception:
            continue
    # Keep each cloud cycle bounded.
    links=list(sorted(links))[:42]
    specialist_mismatch=re.compile(r"(?i)(nuclear|radiation|radiological|explosive|blasting|chemical defense|physician|medical doctor|ulcerative colitis|fpga|vivado|quartus|solidworks|autocad|attorney|public defender|licensed lawyer|political forecaster|accounting advisory|external audit|tax specialist)")
    profile_terms=re.compile(r"(?i)(crm|hubspot|salesforce|revenue operations|revops|marketing|growth|customer success|lifecycle|martech|automation|b2b|saas|campaign|analytics|ga4|seo|prompt engineering|ai evaluation|workflow|operations)")
    def parse_job(url):
        try:
            page=grab(url)
            job=None
            for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',page,re.I|re.S):
                try:d=json.loads(html.unescape(m.group(1)))
                except Exception:continue
                if isinstance(d,dict) and d.get("@type")=="JobPosting": job=d; break
            if not job:return None
            title=job.get("title") or ""
            desc=clean_text(job.get("description") or "")
            quals=clean_text(job.get("qualifications") or "")
            skills=clean_text(job.get("skills") or "")
            txt=" ".join([title,desc,quals,skills])
            if BAD.search(txt) or specialist_mismatch.search(txt):return None
            terms=set(m.group(0).lower() for m in profile_terms.finditer(txt))
            if len(terms)<2:return None
            locs=[z.get("name","") for z in (job.get("applicantLocationRequirements") or []) if isinstance(z,dict)]
            if locs and not any(x.lower() in ("india","worldwide","global","anywhere") for x in locs):return None
            sal=job.get("baseSalary") or {}
            val=(sal.get("value") or {}) if isinstance(sal,dict) else {}
            try:lo=float(val.get("minValue") or val.get("value") or 0)
            except:lo=0
            try:hi=float(val.get("maxValue") or val.get("value") or 0)
            except:hi=0
            amt=hi or lo
            if amt<=0:return None
            unit=str(val.get("unitText") or "").upper()
            openings=int(job.get("totalJobOpenings") or 0)
            org=(job.get("hiringOrganization") or {}).get("name") if isinstance(job.get("hiringOrganization"),dict) else None
            fixed_hint=bool(re.search(r"(?i)(one[- ]time|fixed|paid trial|paid study|paid discovery session)",desc))
            kind="paid-trial" if fixed_hint else "paid-hourly" if unit=="HOUR" else "contract-job"
            # Published pay still requires screening/acceptance; never call it guaranteed.
            multiplier=18 if kind=="paid-trial" else 14 if kind=="paid-hourly" else 8
            fit=len(terms)
            score=amt*multiplier*(1+0.35*fit)*(1+min(openings,100)/500)
            return {
              "source":"nearskill","kind":kind,"title":title,"company":org,"url":url,
              "amount_guess":amt,"currency":sal.get("currency") if isinstance(sal,dict) else None,
              "amount_basis":"fixed" if fixed_hint else ("hourly" if unit=="HOUR" else unit.lower() or "published"),
              "fit":fit,"openings":openings,"locations":locs,"date_posted":job.get("datePosted"),
              "pay_certainty":"PUBLISHED_PAY_SCREENING_REQUIRED","manual_gate":"APPLICATION_OR_SCREENING",
              "score":round(score,2),"action":"APPLY_OR_PREP"
            }
        except Exception:
            return None
    out=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for item in ex.map(parse_job,links):
            if item:out.append(item)
    seen={x["url"]:x for x in out}
    return sorted(seen.values(),key=lambda x:x["score"],reverse=True)[:25]

SOURCES=[
  ("github",github_paid),("laborx",laborx),("nearskill",nearskill),("oneforma",oneforma),
  ("superteam",superteam),("rfp",settle_rfps),("devpost",devpost_api),
  ("security",security_programs),("remoteok",remoteok),("arbeitnow",arbeitnow),
  ("remotive",remotive),("freelancer",freelancer),("braintrust",braintrust),
  ("jobicy",jobicy),("wwr",wwr),("himalayas",himalayas),
  ("hn-intent",hn_intent),("github-intent",github_intent)
]
with concurrent.futures.ThreadPoolExecutor(max_workers=len(SOURCES)) as ex:
    futs={ex.submit(safe,name,fn):name for name,fn in SOURCES}
    source_results=[f.result() for f in concurrent.futures.as_completed(futs)]

all_items=[]
for src in source_results: all_items.extend(src.get("items",[]))
all_items=sorted(all_items,key=lambda x:x.get("score",0),reverse=True)

catalog={}
try:
    catalog=json.loads((ROOT/"config"/"sources.json").read_text())
except Exception:
    catalog={"sources":[]}
catalog_sources=catalog.get("sources",[])
mode_counts={}
category_counts={}
for c in catalog_sources:
    mode=c.get("mode","UNKNOWN")
    category=c.get("category","unknown")
    mode_counts[mode]=mode_counts.get(mode,0)+1
    category_counts[category]=category_counts.get(category,0)+1

native=rust("RTCbc589ef246bc1c5c8c44117f1d66b226f33b9f73")
hosted=rust("Nish916")
total=float(native.get("amount_rtc",0) or 0)+float(hosted.get("amount_rtc",0) or 0)

result={
 "ts":now(),
 "exploration_catalog":{
   "total_sources":len(catalog_sources),
   "mode_counts":mode_counts,
   "category_counts":category_counts,
   "catalog_file":"config/sources.json",
   "intent_dictionary_file":"config/intent-signals.json"
 },
 "payment_floor":{
   "mode":"ZERO_HOUR_EMERGENCY",
   "target":"Maximize probability of at least one legitimate external settlement per hour; never guarantee it.",
   "priority_order":[
     "accepted_or_funded_work",
     "paid_qualification_or_hourly_task",
     "prepaid_fixed_scope_service",
     "warm_buyer_upfront_or_milestone",
     "verified_unassigned_bounty",
     "high_ticket_rfp"
   ],
   "rotation_rule":"Never spend two consecutive cycles on the same blocked source without new evidence.",
   "high_ticket_attention_cap_pct_until_floor":25,
   "minimum_independent_payer_lanes":5,
   "guarantee_definition":"Only accepted/funded fixed-pay work with objective acceptance and no remaining payer discretion can be called guarantee-ready; discovery/application alone never qualifies.",
   "cycle_output":["NOW","NEXT","PARK"]
 },
 "payment_collection":{
   "hub":"https://nishant-payment-hub.vercel.app",
   "commercial_rule":"UPFRONT_OR_FUNDED_MILESTONE",
   "rails":[
     {"name":"INR bank/UPI","status":"AVAILABLE_ON_INVOICE","public_sensitive_details":False},
     {"name":"Wise","status":"ACCOUNT_EXISTS_VERIFY_RECEIVING_DETAILS","public_sensitive_details":False},
     {"name":"PayPal","status":"KYC_SUBMITTED_REVIEW_PENDING_DO_NOT_USE","public_sensitive_details":False},
     {"name":"Toku/Stripe Express","status":"PAYOUT_INFO_REQUIRED","public_sensitive_details":False},
     {"name":"USDC/Base via Coinbase","status":"TRAVEL_RULE_SENDER_INFO_REQUIRED","public_sensitive_details":False}
   ]
 },
 "settlement":{
   "rustchain_native":native,"rustchain_hosted":hosted,"rustchain_total_rtc":total
 },
 "submitted":{
   "cognitive_pr_53":pr("aLexzzz430/Cognitive-OS",53),
   "rustchain_2259":issue("Scottcjn/rustchain-bounties",2259)
 },
 "source_status":[{k:v for k,v in s.items() if k!="items"} for s in sorted(source_results,key=lambda x:x["source"])],
 "queue":{
   "first_cash":[x for x in all_items if x.get("pay_certainty")=="PUBLISHED_PAY_SCREENING_REQUIRED" and x.get("kind") in ("paid-trial","paid-hourly")][:20],
   "high_ticket":[x for x in all_items if x.get("amount_guess",0)>=2500][:12],
   "fast_cash":[x for x in all_items if x.get("kind") in ("paid-hourly","freelance")][:20],
   "buyer_intent":[x for x in all_items if x.get("kind")=="buyer-intent"][:20],
   "contract_jobs":[x for x in all_items if x.get("kind")=="contract-job"][:20],
   "all_ranked":all_items[:60]
 },
 "rules":{
   "count_as_revenue":["authoritative external settlement","payer-confirmed withdrawal-ready balance"],
   "do_not_count":["claim","bid","PR","listing","headline reward","self-transfer","402","unaccepted deliverable"],
   "blocked_lane_policy":"PARK_AND_CONTINUE",
   "exploration_policy":"Continuously add new public payer, freelance, challenge, RFP and buyer-intent sources; failed or blocked sources are parked, not retried aggressively."
 }
}
print(json.dumps(result,indent=2))
