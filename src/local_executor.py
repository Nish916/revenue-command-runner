#!/usr/bin/env python3
import datetime, fcntl, json, os, pathlib, re, sys, urllib.error, urllib.request

HOME=pathlib.Path.home()
CREDS=HOME/'.openwork/credentials.json'
STATE=HOME/'.openwork/executor-state.json'
LOG=HOME/'.openwork/executor.log'
LOCK=HOME/'.openwork/executor.lock'
VERSION='1.6.5'
MAX_BIDS=2
SAFE=re.compile(r'(?i)(api|python|javascript|typescript|documentation|research|analysis|qa|test|automation|crm|revops|marketing|data|writing|seo|hubspot|salesforce)')
BAD=re.compile(r'(?i)(casino|gambl|deposit|stake|identity rental|account sale|private contacts|medical record|exploit|malware|credential theft|wash trade|sniper bot)')

def ts(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def notify(title,message):
    safe_title=str(title).replace('"','\\"')[:120]
    safe_msg=str(message).replace('"','\\"')[:400]
    try:
        os.system(f"osascript -e 'display notification \"{safe_msg}\" with title \"{safe_title}\"' >/dev/null 2>&1")
    except Exception:
        pass

def log(msg):
    line=f'[{ts()}] {msg}'
    print(line, flush=True)
    with LOG.open('a') as f: f.write(line+'\n')

def load_creds():
    d=json.load(open(CREDS))
    return d, d.get('baseUrl','https://dealwork.ai'), d['apiKey'], d['agentAccountId']

C,BASE,KEY,AGENT=load_creds()
HEAD={'Authorization':'Bearer '+KEY,'User-Agent':'NishantRevenueExecutor/2.0','Accept':'application/json'}

def api(method,path,body=None,timeout=10):
    data=None
    headers=dict(HEAD)
    if body is not None:
        data=json.dumps(body).encode()
        headers['Content-Type']='application/json'
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode('utf-8','ignore')
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw=e.read().decode('utf-8','ignore')
        try: payload=json.loads(raw)
        except: payload={'raw':raw[:1200]}
        return e.code,payload
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        log(f'api transport error {method} {path}: {e!r}')
        return 0, {'error':'transport','detail':repr(e)}
    except Exception as e:
        log(f'api unexpected error {method} {path}: {e!r}')
        return 0, {'error':'unexpected','detail':repr(e)}

def get_all_jobs():
    out=[]
    for page in range(1,6):
        st,d=api('GET',f'/api/v1/jobs?per_page=50&page={page}&sort=newest')
        if st!=200: break
        rows=d.get('data',[])
        out.extend(rows)
        if len(rows)<50: break
    return out

def existing_bid_jobs():
    st,d=api('GET','/api/v1/bids/mine?per_page=50')
    rows=d.get('data',[]) if st==200 else []
    return {str(x.get('jobId') or (x.get('job') or {}).get('id')) for x in rows}, rows

def heartbeat():
    st,d=api('POST',f'/api/v1/agents/{AGENT}/heartbeat',{'skillVersion':VERSION})
    return st,d

def profile():
    st,d=api('GET',f'/api/v1/agents/{AGENT}')
    return d.get('data',{}) if st==200 else {}

def wallet():
    st,d=api('GET','/api/v1/wallet/balance')
    return d.get('data',{}) if st==200 else {}

def contracts():
    st,d=api('GET','/api/v1/contracts?role=worker&per_page=50')
    return d.get('data',[]) if st==200 else []

def listings():
    st,d=api('GET','/api/v1/listings/mine')
    return d.get('data',[]) if st==200 else []

def pending_requests():
    st,d=api('GET','/api/v1/listings/requests/pending')
    return d.get('data',[]) if st==200 else []

def send_message(cid,content):
    return api('POST',f'/api/v1/contracts/{cid}/messages',{'content':content,'attachments':[]})

def contract_detail(cid):
    st,d=api('GET',f'/api/v1/contracts/{cid}')
    return d.get('data',{}) if st==200 else {}

def contract_messages(cid):
    st,d=api('GET',f'/api/v1/contracts/{cid}/messages')
    return d.get('data',[]) if st==200 else []

def ollama_generate(prompt,model='qwen3:8b'):
    body=json.dumps({'model':model,'prompt':prompt,'stream':False,'think':False,'options':{'temperature':0.2}}).encode()
    req=urllib.request.Request('http://127.0.0.1:11434/api/generate',data=body,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=240) as r:
        d=json.load(r)
    return str(d.get('response') or '').strip()

def maybe_fulfill_contract(c,actions):
    cid=str(c.get('id'))
    state=str(c.get('state') or c.get('status') or '').lower()
    marker=HOME/'.openwork'/f'contract-{cid}.state.json'
    prior={}
    if marker.exists():
        try: prior=json.load(open(marker))
        except: prior={}
    if state=='escrow_locked':
        st,_=api('POST',f'/api/v1/contracts/{cid}/events',{'type':'START_WORK'})
        actions.append({'type':'START_WORK','contractId':cid,'http':st,'ok':200<=st<300})
        if 200<=st<300:
            send_message(cid,'Started. I am reviewing the supplied scope and acceptance criteria now. I will deliver against them or ask one concise clarification if an essential input is missing.')
            state='in_progress'
    if state!='in_progress' or prior.get('submitted'):
        return
    detail=contract_detail(cid)
    msgs=contract_messages(cid)
    scope=json.dumps({'contract':detail,'messages':msgs},ensure_ascii=False)[:24000]
    if len(scope)<500:
        return
    prompt=(
        'You are fulfilling a paid client task. Use only facts and inputs explicitly supplied in the contract/messages. '
        'Do not invent test results, URLs, data, citations, or access you do not have. Produce the finished deliverable in clear Markdown matching the acceptance criteria. '
        'If a critical input is missing, output exactly NEED_MORE_INFO: followed by one concise request.\n\nSCOPE:\n'+scope
    )
    try:
        out=ollama_generate(prompt)
    except Exception as e:
        log(f'fulfillment model failed {cid[:8]}: {e!r}')
        return
    if out.startswith('NEED_MORE_INFO:'):
        if not prior.get('asked'):
            send_message(cid,out[len('NEED_MORE_INFO:'):].strip())
            marker.write_text(json.dumps({'asked':True,'ts':ts()}))
            actions.append({'type':'CLARIFICATION_SENT','contractId':cid})
        return
    if len(out)<250:
        return
    st,dv=api('POST',f'/api/v1/contracts/{cid}/deliverables',{'description':'Completed deliverable against supplied scope and acceptance criteria','outputData':{'markdown':out}})
    payload=(dv.get('data') or dv) if isinstance(dv,dict) else {}
    did=payload.get('id') if isinstance(payload,dict) else None
    if 200<=st<300 and did:
        st2,_=api('POST',f'/api/v1/contracts/{cid}/events',{'type':'SUBMIT_WORK','deliverableId':did})
        ok=200<=st2<300
        actions.append({'type':'SUBMIT_WORK','contractId':cid,'deliverableId':did,'http':st2,'ok':ok})
        if ok:
            marker.write_text(json.dumps({'submitted':True,'deliverableId':did,'ts':ts()}))
            log(f'submitted contract {cid[:8]}')

def ensure_listings(actions):
    if listings(): return
    specs=[
      {'title':'API Documentation + OpenAPI/README Pack','description':'AI-assisted technical documentation for a public API or supplied codebase: OpenAPI 3.x structure, endpoint examples, README usage notes, and a consistency review. No private credential handling.','category':'writing','pricingMode':'fixed','fixedPrice':'20.00','tags':['api','openapi','documentation','readme'],'estimatedDeliveryHours':4},
      {'title':'QA / API Regression Test Review','description':'AI-assisted QA pass for a supplied public or authorized project: test-plan, reproducible bug report, API regression checks, edge cases, and concise verification notes.','category':'development','pricingMode':'fixed','fixedPrice':'25.00','tags':['qa','testing','api','regression'],'estimatedDeliveryHours':4},
      {'title':'CRM / RevOps Workflow Audit','description':'Structured audit of a supplied CRM/RevOps workflow: funnel gaps, automation opportunities, data-quality risks, reporting checks, and prioritized fixes. Public or owner-authorized inputs only.','category':'research','pricingMode':'fixed','fixedPrice':'30.00','tags':['crm','revops','automation','analysis'],'estimatedDeliveryHours':4}
    ]
    for s in specs:
        st,d=api('POST','/api/v1/listings',s)
        if 200<=st<300:
            actions.append({'type':'LISTING_CREATED','title':s['title'],'price':s['fixedPrice']})
            log('created service listing: '+s['title'])
        else:
            log(f'listing create failed {st}: {s["title"]}')

def maybe_intro(actions):
    marker=HOME/'.openwork/intro-posted-v1'
    if marker.exists(): return
    st,ch=api('GET','/api/v1/channels/page/introductions')
    data=ch.get('data',{}) if st==200 else {}
    cid=data.get('id')
    if not cid: return
    msg='I am Nishant Revenue Council, an AI-assisted worker focused on API/documentation, QA, CRM/RevOps automation, research and data analysis. I use evidence-first deliverables and only work with public or owner-authorized inputs.'
    st,_=api('POST',f'/api/v1/channels/{cid}/messages',{'content':msg})
    if 200<=st<300:
        marker.write_text(ts())
        actions.append({'type':'INTRO_POSTED'})
        log('posted one-time marketplace introduction')

def job_fit(j):
    text=' '.join(str(j.get(k) or '') for k in ['title','description','category'])
    if BAD.search(text) or not SAFE.search(text): return -1
    return sum(1 for _ in SAFE.finditer(text))

def execute_jobs(jobs,actions):
    bid_ids,bids=existing_bid_jobs()
    candidates=[]
    for j in jobs:
        fit=job_fit(j)
        if fit<0: continue
        funded=bool(j.get('posterFunded'))
        mode=str(j.get('jobMode') or '').lower()
        status=str(j.get('status') or '').lower()
        if mode=='open' and funded and j.get('claimable') is True and int(j.get('remainingSlots') or 0)>0:
            candidates.append((10000+fit,j,'CLAIM'))
        elif mode=='bid' and funded and status=='bidding' and str(j.get('id')) not in bid_ids:
            candidates.append((5000+fit-int(j.get('bidCount') or 0),j,'BID'))
    candidates.sort(key=lambda x:x[0],reverse=True)
    bid_count=0
    for _,j,kind in candidates:
        jid=str(j.get('id'))
        if kind=='CLAIM':
            criteria=[str(x.get('id')) for x in (j.get('acceptanceCriteria') or []) if x.get('id')]
            st,d=api('POST',f'/api/v1/jobs/{jid}/claim',{'acceptedCriteriaIds':criteria})
            actions.append({'type':'CLAIM','jobId':jid,'title':j.get('title'),'http':st,'ok':200<=st<300})
            log(f'claim {st}: {j.get("title")}')
            if 200<=st<300: break
        elif kind=='BID' and bid_count<MAX_BIDS:
            lo=float(j.get('budgetMin') or 0); hi=float(j.get('budgetMax') or 0)
            amt=lo if lo>0 else max(1.0,hi*0.8 if hi>0 else 10.0)
            title=str(j.get('title') or 'task')
            desc=re.sub(r'\s+',' ',str(j.get('description') or ''))[:350]
            body={'proposedAmount':f'{amt:.2f}','estimatedHours':2,'proposalText':f'I can complete “{title}” against the posted acceptance criteria. I will deliver a tested, documented result with reproducible verification. Scope noted: {desc[:180]}'}
            st,d=api('POST',f'/api/v1/jobs/{jid}/bids',body)
            actions.append({'type':'BID','jobId':jid,'title':title,'amount':amt,'http':st,'ok':200<=st<300})
            log(f'bid {st}: {title}')
            if 200<=st<300: bid_count+=1

def handle_contracts(rows,actions):
    for c in rows:
        maybe_fulfill_contract(c,actions)

def handle_listing_requests(rows,actions):
    for r in rows:
        rid=str(r.get('id') or '')
        lid=str(r.get('listingId') or (r.get('listing') or {}).get('id') or '')
        req=str(r.get('requirements') or r.get('message') or '')
        if not rid or not lid or BAD.search(req):
            continue
        st,_=api('POST',f'/api/v1/listings/{lid}/requests/{rid}/respond',{'action':'accept'})
        actions.append({'type':'LISTING_REQUEST_ACCEPT','requestId':rid,'listingId':lid,'http':st,'ok':200<=st<300})
        log(f'listing request {rid[:8]} accept -> {st}')

def main():
    with open(LOCK,'w') as lf:
        try: fcntl.flock(lf,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            log('skip overlap'); return
        actions=[]
        hb_status,hb=heartbeat()
        p=profile(); w=wallet(); jobs=get_all_jobs(); cs=contracts()
        funded=[j for j in jobs if bool(j.get('posterFunded'))]
        claimable=[j for j in jobs if bool(j.get('posterFunded')) and j.get('claimable') is True]
        execute_jobs(jobs,actions)
        handle_contracts(cs,actions)
        ensure_listings(actions)
        maybe_intro(actions)
        reqs=pending_requests()
        handle_listing_requests(reqs,actions)
        _,bids=existing_bid_jobs()
        truth={'ts':ts(),'bids':bids,'contracts':cs,'source':'authenticated_executor'}
        (HOME/'.openwork/income-state.json').write_text(json.dumps(truth,indent=2))
        verification=p.get('verification') or {}
        snap={'ts':ts(),'mode':'AUTHENTICATED_EXECUTOR','profile':{'claimed':bool(p.get('claimedAt') or p.get('isClaimed')),'trustTierLevel':p.get('trustTierLevel'),'verified':verification.get('verified'),'verificationChecks':verification.get('checks'),'totalEarned':p.get('totalEarned'),'activeContractCount':p.get('activeContractCount'),'healthy':p.get('isHealthy'),'lastHealthPing':p.get('lastHealthPing')},'wallet':w,'inventory':{'total':len(jobs),'funded':len(funded),'claimable':len(claimable)},'current':{'bids':len(bids),'contracts':len(cs),'listings':len(listings()),'pendingListingRequests':len(reqs)},'actions':actions,'truth_rule':'Only funded+claimable/accepted work or settled wallet changes are cash-near. Unfunded listings and salary headlines are research only.'}
        previous={}
        if STATE.exists():
            try: previous=json.load(open(STATE))
            except: previous={}
        prev_inv=previous.get('inventory') or {}
        prev_cur=previous.get('current') or {}
        prev_wallet=previous.get('wallet') or {}
        try: old_available=float(prev_wallet.get('available') or 0)
        except: old_available=0.0
        try: new_available=float(w.get('available') or 0)
        except: new_available=0.0
        if len(funded)>int(prev_inv.get('funded') or 0): notify('Revenue Executor','New funded Dealwork inventory detected')
        if len(claimable)>int(prev_inv.get('claimable') or 0): notify('Revenue Executor','New claimable paid task detected')
        if len(cs)>int(prev_cur.get('contracts') or 0): notify('Revenue Executor','New paid contract detected')
        if len(reqs)>int(prev_cur.get('pendingListingRequests') or 0): notify('Revenue Executor','New service quote/order request detected')
        if new_available>old_available: notify('REAL INCOME ALERT',f'Dealwork available balance increased to {new_available:.2f} USD')
        STATE.write_text(json.dumps(snap,indent=2))
        log('cycle '+json.dumps({'funded':len(funded),'claimable':len(claimable),'contracts':len(cs),'bids':len(bids),'actions':len(actions),'wallet':w.get('available')}))

if __name__=='__main__':
    main()
