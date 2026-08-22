from __future__ import annotations
import csv, hashlib, json, re, sys, time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

OUT=Path('whs_inventory'); OUT.mkdir(exist_ok=True)
BASE='https://biblicalstudies.gospelstudies.org.uk/articles_whs_{:02d}.php'
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 BSUK academic archive inventory/1.0'})

pages=[]; consecutive_missing=0
for i in range(1,31):
    u=BASE.format(i)
    try:
        r=s.get(u,timeout=30,allow_redirects=True)
        ok=r.status_code==200 and 'Proceedings of the Wesley Historical Society' in r.text
    except Exception as e:
        ok=False; r=None
    if ok:
        pages.append((i,u,r.text)); consecutive_missing=0
        print(f'PAGE_OK {i:02d} {u}',flush=True)
    else:
        consecutive_missing += 1
        print(f'PAGE_MISSING {i:02d} status={getattr(r,"status_code",None)}',flush=True)
        if i>13 and consecutive_missing>=3: break

records=[]
for pi,page_url,html in pages:
    soup=BeautifulSoup(html,'html.parser')
    current_volume=None
    for node in soup.find_all(['h1','h2','h3','h4','a']):
        if node.name in ('h1','h2','h3','h4'):
            txt=' '.join(node.stripped_strings)
            m=re.search(r'\bVolume\s+(\d+)\b',txt,re.I)
            if m: current_volume=int(m.group(1))
            continue
        a=node; href=(a.get('href') or '').strip(); atxt=' '.join(a.stripped_strings)
        if not href: continue
        low=(href+' '+atxt).lower()
        # PDF candidates only. Ignore ZIP/download-all links.
        if '.pdf' not in low and not re.search(r'\bpdf\b',atxt,re.I): continue
        absu=urljoin(page_url,href)
        # Include direct PDF-ish URLs; the GET validation below is authoritative.
        context=' '.join((a.parent.get_text(' ',strip=True) if a.parent else atxt).split())
        issue_m=re.search(r'\b(\d{1,2})\.(\d+(?:[-–]\d+)?(?:\([ivx]+\))?)\b',context,re.I)
        issue_label=(issue_m.group(1)+'.'+issue_m.group(2)) if issue_m else ''
        is_issue=bool(re.search(r'view this issue',context,re.I))
        label=atxt or context[:180]
        records.append({'page':pi,'page_url':page_url,'volume':current_volume if current_volume else 0,'url':absu,'anchor':atxt,'context':context[:700],'issue_label':issue_label,'is_issue':is_issue})

# Deduplicate repeated navigation/global links by source URL before network validation.
by_url={}
for rec in records:
    by_url.setdefault(rec['url'],rec)
for rec in records:
    by_url[rec['url']].setdefault('seen_on_pages',[])
    if rec['page'] not in by_url[rec['url']]['seen_on_pages']: by_url[rec['url']]['seen_on_pages'].append(rec['page'])
unique=list(by_url.values())
print(f'RAW_PDF_LINK_OCCURRENCES {len(records)}',flush=True)
print(f'UNIQUE_SOURCE_URLS {len(unique)}',flush=True)

hash_first={}; valid=[]; broken=[]
for idx,rec in enumerate(unique,1):
    u=rec['url']; h=hashlib.sha256(); size=0; first=b''; status=None; final=''; ctype=''; err=''
    try:
        with s.get(u,timeout=90,allow_redirects=True,stream=True) as r:
            status=r.status_code; final=r.url; ctype=r.headers.get('content-type','')
            r.raise_for_status()
            for chunk in r.iter_content(1024*1024):
                if not chunk: continue
                if len(first)<8: first=(first+chunk)[:8]
                size+=len(chunk); h.update(chunk)
        sha=h.hexdigest(); pdf_ok=first.startswith(b'%PDF-') and size>=1024
        rec.update(status=status,final_url=final,content_type=ctype,size=size,sha256=sha,pdf_magic=first[:5].decode('latin1','replace'),valid_pdf=pdf_ok,error='')
        if pdf_ok:
            if sha in hash_first: rec['duplicate_content_of']=hash_first[sha]
            else: hash_first[sha]=u; rec['duplicate_content_of']=''
            valid.append(rec)
        else:
            rec['error']=f'not-valid-pdf magic={first!r} size={size}'; broken.append(rec)
    except Exception as e:
        rec.update(status=status,final_url=final,content_type=ctype,size=size,sha256='',pdf_magic=first[:5].decode('latin1','replace'),valid_pdf=False,error=repr(e),duplicate_content_of=''); broken.append(rec)
    print(f"CHECK {idx}/{len(unique)} V{rec['volume']:02d} {'OK' if rec['valid_pdf'] else 'BAD'} size={size} {u}",flush=True)

# Unique content is the authoritative PDF corpus.
content_unique=[]; seen_sha=set()
for r in valid:
    if r['sha256'] in seen_sha: continue
    seen_sha.add(r['sha256']); content_unique.append(r)

per_volume=Counter(); issues=Counter(); global_recs=[]
for r in content_unique:
    if r['volume']:
        per_volume[r['volume']]+=1
        if r['is_issue']: issues[r['volume']]+=1
    else: global_recs.append(r)

double_issues=[]
for r in content_unique:
    if r['is_issue'] and re.search(r'[-–]',r['issue_label']): double_issues.append(r['issue_label'])

dup_urls=[r for r in by_url.values() if len(r.get('seen_on_pages',[]))>1]
dup_content=[r for r in valid if r.get('duplicate_content_of')]
summary={
 'pages_found':[p[0] for p in pages],
 'raw_pdf_link_occurrences':len(records),
 'unique_source_urls':len(unique),
 'valid_pdf_urls':len(valid),
 'broken_pdf_urls':len(broken),
 'unique_pdf_contents':len(content_unique),
 'duplicate_content_count':len(dup_content),
 'duplicate_url_across_pages_count':len(dup_urls),
 'volumes_with_content':sorted(per_volume),
 'per_volume_pdf_counts':{str(k):per_volume[k] for k in sorted(per_volume)},
 'per_volume_issue_unit_counts':{str(k):issues[k] for k in sorted(issues)},
 'total_issue_units':sum(issues.values()),
 'global_unique_pdf_count':len(global_recs),
 'global_pdfs':[{'url':r['url'],'anchor':r['anchor'],'sha256':r['sha256'],'size':r['size']} for r in global_recs],
 'double_issue_labels':double_issues,
 'broken':[{'url':r['url'],'status':r.get('status'),'error':r.get('error')} for r in broken],
 'duplicate_content':[{'url':r['url'],'same_as':r.get('duplicate_content_of'),'sha256':r.get('sha256')} for r in dup_content],
 'duplicate_urls_across_pages':[{'url':r['url'],'pages':r.get('seen_on_pages')} for r in dup_urls],
}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
fields=['page','volume','issue_label','is_issue','url','final_url','status','content_type','size','sha256','pdf_magic','valid_pdf','duplicate_content_of','seen_on_pages','anchor','context','error']
with (OUT/'inventory.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader();
    for r in unique: w.writerow(r)
print('===WHS_SUMMARY_JSON===',flush=True)
print(json.dumps(summary,ensure_ascii=False,sort_keys=True),flush=True)
print('===END_WHS_SUMMARY===',flush=True)
if broken:
    print(f'WARNING broken={len(broken)}; inventory completed with anomalies',flush=True)
