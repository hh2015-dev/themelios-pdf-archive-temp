import os,re,json,hashlib,time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

PAGE='https://biblicalstudies.org.uk/articles_themelios-ifes.php'
MIRROR='https://biblicalstudies.gospelstudies.org.uk/articles_themelios-ifes.php'
OUT='themelios_ifes_archive'
os.makedirs(OUT,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK archive'})

def fetch_page():
    for u in (PAGE,MIRROR):
        try:
            r=S.get(u,timeout=30); r.raise_for_status()
            if 'Themelios' in r.text: return r,u
        except Exception: pass
    raise RuntimeError('index fetch failed')

r,base=fetch_page(); soup=BeautifulSoup(r.text,'html.parser')
items=[]; seen=set(); errors=[]
for a in soup.find_all('a',href=True):
    href=a['href'].strip(); label=' '.join(a.get_text(' ',strip=True).split())
    if '.pdf' not in href.lower(): continue
    url=urljoin(base,href)
    if url in seen: continue
    seen.add(url)
    m=re.search(r'Themelios\s+(\d+)\.(\d+(?:/\d+)?)\s*\((\d{4})\)',label,re.I)
    if not m:
        m=re.search(r'Themelios\s+(\d+)\.(\d+(?:/\d+)?)',label,re.I)
    if not m:
        continue
    vol=int(m.group(1)); issue=m.group(2); year=int(m.group(3)) if len(m.groups())>=3 and m.group(3) else None
    fn=os.path.basename(url.split('?')[0]) or f'v{vol}_{issue}.pdf'
    vdir=os.path.join(OUT,f'Volume {vol:03d}'); os.makedirs(vdir,exist_ok=True)
    path=os.path.join(vdir,fn)
    ok=False; last=''
    for attempt in range(3):
        try:
            rr=S.get(url,timeout=60)
            if rr.status_code==200 and rr.content.startswith(b'%PDF'):
                open(path,'wb').write(rr.content); ok=True; break
            last=f'status={rr.status_code} head={rr.content[:20]!r}'
        except Exception as e: last=repr(e)
        time.sleep(1+attempt)
    if not ok:
        errors.append({'url':url,'label':label,'error':last}); continue
    data=open(path,'rb').read()
    items.append({'volume':vol,'issue':issue,'year':year,'label':label,'url':url,'file':fn,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})

json.dump(items,open(os.path.join(OUT,'manifest.json'),'w'),ensure_ascii=False,indent=2)
json.dump(errors,open(os.path.join(OUT,'errors.json'),'w'),ensure_ascii=False,indent=2)
summary={'unique_pdfs':len(items),'errors':len(errors),'volumes':sorted(set(x['volume'] for x in items)),'by_volume':{str(v):sum(1 for x in items if x['volume']==v) for v in sorted(set(x['volume'] for x in items))}}
json.dump(summary,open(os.path.join(OUT,'summary.json'),'w'),indent=2)
print(json.dumps(summary,indent=2))
if errors: raise SystemExit(2)
