import os,re,time,requests,fitz,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin,urlparse

BASE='https://biblicalstudies.gospelstudies.org.uk/'
PAGES=[urljoin(BASE,'articles_evangelical_quarterly.php')]+[urljoin(BASE,f'articles_evangelical_quarterly-{i:02d}.php') for i in range(1,9)]
S=requests.Session();S.headers['User-Agent']='Mozilla/5.0 BSUK archival worker'
BROKEN_EXPECTED=9; TOTAL_LINKS=1494; TARGET=1485; SKIP_VOLUME=1

def clean(s): return ' '.join(str(s).split())
def safe(s):
    s=s.replace('–','-').replace('—','-')
    s=re.sub(r'[\\/:*?"<>|]+',' - ',s); s=re.sub(r'\s+',' ',s).strip(' .-')
    return s[:155].rstrip(' .-')
def context(a):
    p=a.parent
    best=clean(p.get_text(' ',strip=True)) if p else ''
    for _ in range(6):
        if not p:break
        t=clean(p.get_text(' ',strip=True))
        if 'Evangelical Quarterly' in t and len(t)<1800: best=t; break
        p=p.parent
    return best
def parse_title(c):
    j=re.search(r'(?:The\s+)?Evangelical Quarterly',c,re.I)
    if not j:return None
    pre=c[:j.start()].strip(' ,')
    # Prefer quoted title, allowing a missing closing quote.
    qs=[pre.rfind('"'),pre.rfind('“')]; q=max(qs)
    if q>=0:return clean(pre[q+1:].strip(' "“”,')) or None
    # Fallback: author metadata before first comma, title after it.
    if ',' in pre:return clean(pre.split(',',1)[1].strip(' "“”,')) or None
    return None
def parse_meta(c,url):
    # Find vol/issue with flexible punctuation: 61:1, 62 3, normal 63.2.
    m=re.search(r'(?:The\s+)?Evangelical Quarterly\s+(\d+)\s*[\.: ]\s*(\d+)\b',c,re.I)
    vol=int(m.group(1)) if m else None; issue=int(m.group(2)) if m else None
    # year from citation, otherwise internal filename.
    ym=re.search(r'\b((?:19|20)\d{2})(?:/\d{2})?\b',c)
    year=int(ym.group(1)) if ym else None
    bn=urlparse(url).path.rsplit('/',1)[-1]
    fm=re.match(r'((?:19|20)\d{2})-(\d+)[_-]',bn)
    if fm:
        fy,fi=map(int,fm.groups()); year=year or fy; issue=issue or fi
        # For 1929-2015 EQ volume maps exactly to year-1928; fixes known site citation typo 46.2->45.2.
        if 1929<=fy<=2015: vol=fy-1928
    # pages = last numeric range before pdf/end, robust to colon/comma punctuation.
    ranges=re.findall(r'\b(\d{1,4})\s*[-–]\s*(\d{1,4})\b',c)
    pages=f'{ranges[-1][0]}-{ranges[-1][1]}' if ranges else None
    title=parse_title(c)
    return vol,issue,year,pages,title

def discover():
    out=[]
    for page in PAGES:
        r=S.get(page,timeout=60);r.raise_for_status();soup=BeautifulSoup(r.text,'html.parser')
        for a in soup.find_all('a',href=True):
            if '.pdf' not in a['href'].lower():continue
            u=urljoin(page,a['href']);c=context(a);v,i,y,pp,t=parse_meta(c,u)
            out.append({'url':u,'volume':v,'issue':i,'year':y,'pages':pp,'title':t,'context':c})
    uniq={x['url']:x for x in out}; out=list(uniq.values())
    if len(out)!=TOTAL_LINKS:raise RuntimeError(f'Expected {TOTAL_LINKS} links got {len(out)}')
    badmeta=[x for x in out if not all([x['volume'],x['issue'],x['year'],x['pages'],x['title']])]
    if badmeta:
        print('BADMETA='+json.dumps(badmeta,ensure_ascii=False),flush=True);raise RuntimeError(f'Unparsed metadata {len(badmeta)}')
    names={}
    for x in out:
        fn=f"The Evangelical Quarterly - Volume {x['volume']:03d} Issue {x['issue']:02d} - {x['year']} - {safe(x['title'])} - pp {x['pages']}.pdf"
        x['filename']=fn
        if fn in names and names[fn]!=x['url']:raise RuntimeError('Filename collision '+fn)
        names[fn]=x['url']
    return out

def dl(x):
    if x['volume']==SKIP_VOLUME:return ('skip',x,None)
    group=((x['volume']-1)//10)*10+1; group_end=min(group+9,87)
    d=Path(f'eq_bulk/v{group:03d}-{group_end:03d}/Volume {x["volume"]:03d}');d.mkdir(parents=True,exist_ok=True)
    p=d/x['filename']; err=None
    for n in range(4):
        try:
            with S.get(x['url'],stream=True,timeout=(30,180)) as r:
                if r.status_code==404:return ('broken',x,404)
                r.raise_for_status()
                with open(p,'wb') as f:
                    for b in r.iter_content(1024*1024):
                        if b:f.write(b)
            with open(p,'rb') as f:
                if f.read(5)!=b'%PDF-':raise RuntimeError('not PDF')
            d0=fitz.open(p);pc=d0.page_count;d0.close()
            if pc<1:raise RuntimeError('zero pages')
            return ('ok',x,pc)
        except Exception as e:
            err=e
            try:p.unlink()
            except OSError:pass
            time.sleep(2*(n+1))
    return ('error',x,repr(err))

rows=discover(); print('DISCOVERED=1494',flush=True)
counts={'ok':0,'broken':0,'skip':0,'error':0};broken=[];errors=[];done=0
with ThreadPoolExecutor(max_workers=4) as ex:
    fs={ex.submit(dl,x):x for x in rows}
    for f in as_completed(fs):
        st,x,extra=f.result();counts[st]+=1
        if st=='broken':broken.append(x)
        if st=='error':errors.append((x,extra))
        if st in ('ok','broken'):done+=1; print(f'{done}/{TARGET-26+BROKEN_EXPECTED}|{done/(TARGET-26+BROKEN_EXPECTED)*100:.1f}%|{st}|V{x["volume"]:03d} I{x["issue"]:02d}|{x["filename"]}',flush=True)
print('COUNTS='+json.dumps(counts),flush=True)
print('BROKEN='+json.dumps(broken,ensure_ascii=False),flush=True)
if errors: print('ERRORS='+json.dumps(errors,ensure_ascii=False),flush=True);raise SystemExit(2)
if counts['broken']!=BROKEN_EXPECTED:raise RuntimeError(f'Expected {BROKEN_EXPECTED} broken got {counts["broken"]}')
if counts['ok']!=TARGET-26:raise RuntimeError(f'Expected {TARGET-26} downloaded after V1 got {counts["ok"]}')
Path('eq_bulk/manifest_complete.json').write_text(json.dumps({'counts':counts,'broken':broken},ensure_ascii=False,indent=2),encoding='utf8')
print('BULK_COMPLETE='+str(counts['ok']),flush=True)
