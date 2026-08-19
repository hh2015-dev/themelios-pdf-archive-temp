import os,re,requests,fitz
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin

PAGE='https://biblicalstudies.gospelstudies.org.uk/articles_evangelical_quarterly.php'
OUT=Path('eq_volume_001'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 BSUK archival worker'
CIT=re.compile(r'Evangelical Quarterly\s+1\.([1-4])\s*\(([^)]*?1929[^)]*)\)[,:]\s*([0-9]+(?:\s*[-–]\s*[0-9]+)?)',re.I)

def clean(s): return ' '.join(s.split())
def title_from(c):
    m=re.search(r'["“](.+?)["”]\s*,?\s*(?:The\s+)?Evangelical Quarterly',c,re.I)
    if m:return clean(m.group(1)).rstrip(',')
    # malformed missing closing quote: text between first quote and EQ
    m=re.search(r'["“](.+?)\s+(?:The\s+)?Evangelical Quarterly',c,re.I)
    return clean(m.group(1)).rstrip(',') if m else 'Untitled'
def safe(s):
    s=re.sub(r'[\\/:*?"<>|]+',' - ',s); s=re.sub(r'\s+',' ',s).strip(' .-')
    return s[:170]
def get_context(a):
    p=a.parent
    for _ in range(5):
        if not p: break
        t=clean(p.get_text(' ',strip=True))
        if 'Evangelical Quarterly' in t and len(t)<1500:return t
        p=p.parent
    return clean(a.parent.get_text(' ',strip=True))

def meta(a):
    c=get_context(a); m=CIT.search(c)
    if not m:
        # known punctuation variant (, before pages)
        m=re.search(r'Evangelical Quarterly\s+1\.([1-4])\s*\(([^)]*1929[^)]*)\)\s*[,;:]\s*([0-9]+(?:\s*[-–]\s*[0-9]+)?)',c,re.I)
    if not m: raise RuntimeError('Unparsed: '+c)
    issue=int(m.group(1)); pages=m.group(3).replace('–','-').replace(' ',''); title=title_from(c)
    fn=f'The Evangelical Quarterly - Volume 001 Issue {issue:02d} - 1929 - {safe(title)} - pp {pages}.pdf'
    return c,fn

def dl(item):
    url,fn=item; p=OUT/fn
    with S.get(url,stream=True,timeout=(30,180)) as r:
        r.raise_for_status();
        with open(p,'wb') as f:
            for b in r.iter_content(1024*1024):
                if b:f.write(b)
    if open(p,'rb').read(5)!=b'%PDF-': raise RuntimeError('not PDF '+url)
    d=fitz.open(p); n=d.page_count; d.close()
    if n<1: raise RuntimeError('zero pages '+url)
    return fn,n,p.stat().st_size

r=S.get(PAGE,timeout=60);r.raise_for_status();soup=BeautifulSoup(r.text,'html.parser')
items=[]
for a in soup.find_all('a',href=True):
    href=a['href']
    if '.pdf' not in href.lower():continue
    c=get_context(a)
    if not re.search(r'Evangelical Quarterly\s+1\.[1-4]\b',c,re.I):continue
    _,fn=meta(a);items.append((urljoin(PAGE,href),fn))
items=list(dict.fromkeys(items))
print('TARGET='+str(len(items)),flush=True)
if len(items)!=26: raise RuntimeError(f'Expected 26 got {len(items)}')
with ThreadPoolExecutor(max_workers=4) as ex:
    fs={ex.submit(dl,x):x for x in items}; done=0
    for f in as_completed(fs):
        fn,n,sz=f.result();done+=1; print(f'{done}/26|{done/26*100:.1f}%|{fn}|pages={n}|bytes={sz}',flush=True)
print('COMPLETE=26',flush=True)
