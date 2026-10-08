#!/usr/bin/env python3
import json, re, subprocess, os
from datetime import datetime, timezone, timedelta

OUT='/Users/cashify/revenue-radar/github_candidates.json'
LOG='/Users/cashify/revenue-radar/github_radar.log'
GH='/opt/homebrew/bin/gh'
ME='Nish916'
since=(datetime.now(timezone.utc)-timedelta(days=60)).date().isoformat()
queries=[
    f'is:issue is:open label:bounty updated:>={since}',
    f'is:issue is:open in:title bounty updated:>={since}',
    f'is:issue is:open "USDC bounty" updated:>={since}',
]
ban_repos=re.compile(r'(?i)(bounty-plaza|rustchain-bounties|arbitr$|bounty[-_]?radar|claim[-_]?tracker|earnings[-_]?radar|bountyscout|/gh-disc-)')
ban_text=re.compile(r'(?i)(\[bounty claim\]|\[bounty proposal\]|bounty alert:|bug fix submission|this submission is for the bounty|payout request|consolidated bounty claim|claiming\s+(?:this\s+)?bounty|payout system broken|stuck in review|completed verification|qualification:|radar\]|upfront payment confirmed|urgent.*999999|casino|gambl|trade.*to earn|deposit.*to earn)')
assigned_text=re.compile(r'(?i)\bassigned\s+to\s+(?:\[\s*)?@?[A-Za-z0-9-]+')
reward_patterns=[
    re.compile(r'(?i)(?:/bounty|\bbounty\b|\breward\b)(?:\s+(?:of|is|worth))?\s*[:=\-]?\s*\$\s*([0-9][0-9,]*(?:\.\d+)?)([kKmM]?)\s*(?:USD|USDC)?'),
    re.compile(r'(?i)(?:/bounty|\bbounty\b|\breward\b)(?:\s+(?:of|is|worth))?\s*[:=\-]?\s*([0-9][0-9,]*(?:\.\d+)?)([kKmM]?)\s*(?:USD|USDC)\b'),
    re.compile(r'(?i)\$\s*([0-9][0-9,]*(?:\.\d+)?)([kKmM]?)\s*(?:USD|USDC)?\s+(?:gross\s+)?(?:bounty|reward)\b'),
    re.compile(r'(?i)([0-9][0-9,]*(?:\.\d+)?)([kKmM]?)\s*(?:USD|USDC)\s+(?:gross\s+)?(?:bounty|reward)\b'),
]

def api(args):
    return subprocess.check_output([GH,'api','-X','GET']+args,text=True,stderr=subprocess.STDOUT,timeout=45)

def parse_amount(text):
    values=[]
    for pattern in reward_patterns:
        for match in pattern.finditer(text):
            try:
                value=float(match.group(1).replace(',',''))
                suffix=(match.group(2) or '').lower()
                if suffix=='k': value*=1000
                elif suffix=='m': value*=1000000
                values.append((value, match.group(0)[:140]))
            except Exception:
                pass
    if not values:
        return 0, None
    return max(values, key=lambda item:item[0])

seen={}
errors=0
for q in queries:
    try:
        data=json.loads(api(['search/issues','-f','q='+q,'-f','per_page=100']))
        for it in data.get('items',[]): seen[it['html_url']]=it
    except Exception as e:
        errors+=1
        open(LOG,'a').write('{} query_error {!r} {}\n'.format(datetime.now().isoformat(),q,e))

if not seen and errors:
    open(LOG,'a').write('{} search_unavailable errors={} preserving_previous_output\n'.format(datetime.now().isoformat(),errors))
    raise SystemExit(0)

cands=[]
for it in seen.values():
    url=it.get('html_url','')
    m=re.search(r'github\.com/([^/]+/[^/]+)/issues/(\d+)',url)
    if not m:
        continue
    repo=m.group(1)
    title=it.get('title','')
    body=it.get('body') or ''
    txt=title+'\n'+body
    author=((it.get('user') or {}).get('login') or '')
    association=str(it.get('author_association') or '').upper()
    assignees=[(x or {}).get('login') for x in (it.get('assignees') or []) if isinstance(x,dict)]
    if author.lower()==ME.lower():
        continue
    if association not in {'OWNER','MEMBER','COLLABORATOR'}:
        continue
    if assignees and ME not in assignees:
        continue
    if assigned_text.search(txt) and ME not in assignees:
        continue
    if ban_repos.search(repo) or ban_text.search(txt):
        continue
    amt, evidence=parse_amount(txt)
    if amt<50 or amt>100000:
        continue
    cands.append({
        'repo':repo,'number':int(m.group(2)),'amount':amt,'title':title,'url':url,
        'updated_at':it.get('updated_at'),'comments':it.get('comments',0),
        'author':author,'author_association':association,'assignees':assignees,'reward_evidence':evidence,
        'body_excerpt':body[:1400]
    })

cands=sorted(cands,key=lambda x:(x['amount'],x['updated_at'] or ''),reverse=True)[:50]
verified=[]
for x in cands:
    try:
        r=json.loads(api(['repos/'+x['repo']]))
        x['repo_stars']=r.get('stargazers_count',0)
        x['repo_forks']=r.get('forks_count',0)
        x['repo_created_at']=r.get('created_at')
        x['repo_archived']=r.get('archived',False)
        x['owner_type']=(r.get('owner') or {}).get('type')
        x['trust_score']=(0 if x['repo_archived'] else 1)+(1 if x['repo_stars']>=5 else 0)+(1 if x['repo_forks']>=2 else 0)+(1 if x['comments']>=1 else 0)
        if x['trust_score']>=2:
            verified.append(x)
    except Exception as e:
        x['verify_error']=type(e).__name__

verified=sorted(verified,key=lambda x:(x['trust_score'],x['amount'],x['updated_at'] or ''),reverse=True)
payload={
    'scanned_at':datetime.now(timezone.utc).isoformat(),
    'raw_hits':len(seen),
    'reward_signaled':len(cands),
    'verified_count':len(verified),
    'policy':'Explicit bounty/reward amounts only; skip self-authored and already-assigned issues.',
    'top':verified[:30]
}
tmp=OUT+'.tmp'
open(tmp,'w').write(json.dumps(payload,indent=2))
os.replace(tmp,OUT)
open(LOG,'a').write('{} raw={} reward_signaled={} verified={}\n'.format(datetime.now().isoformat(),len(seen),len(cands),len(verified)))
