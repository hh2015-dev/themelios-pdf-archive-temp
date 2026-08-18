import re,json,pathlib,time,io
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pypdf import PdfReader,PdfWriter
BASE='https://jbtsonline.org/'; ISSUES=urljoin(BASE,'issues/')
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK-JBTS-Archiver/1.0'})
out=pathlib.Path('jbts_out'); out.mkdir(exist_ok=True)
def get(url,timeout=60):
    last=None
    for i in range(3):
        try:
            r=S.get(url,timeout=timeout,allow_redirects=True)
            if r.status_code<500:return r
            last=f'HTTP {r.status_code}'
        except Exception as e:last=repr(e)
        time.sleep(2+i)
    raise RuntimeError(f'GET failed {url}: {last}')
def txt(x):return re.sub(r'\s+',' ',x.get_text(' ',strip=True)).strip()
def pages(data):return len(PdfReader(io.BytesIO(data)).pages)
def pdf_from(url):
    r=get(url); ct=(r.headers.get('content-type') or '').lower()
    if r.content.startswith(b'%PDF') or 'application/pdf' in ct:return r.url,r.content
    soup=BeautifulSoup(r.text,'html.parser'); c=[]
    for a in soup.find_all('a',href=True):
        h=urljoin(r.url,a['href']); t=txt(a).lower()
        if h.lower().split('?')[0].endswith('.pdf'):
            sc=(10 if 'full issue' in t else 0)+(4 if 'pdf' in t else 0)+(2 if '/files/' in h.lower() else 0)
            c.append((sc,h))
    for _,h in sorted(c,reverse=True):
        rr=get(h)
        if rr.content.startswith(b'%PDF'):return rr.url,rr.content
    return None,None
soup=BeautifulSoup(get(ISSUES).text,'html.parser')
heads=[h for h in soup.find_all(['h2','h3']) if re.match(r'^JBTS Volume\s+\d+',txt(h),re.I)]
secs={}
for h in heads:
    m=re.search(r'Volume\s+(\d+)(?:\s*\|\s*Issue\s*(\d+))?',txt(h),re.I)
    if not m:continue
    key=(int(m.group(1)),int(m.group(2)) if m.group(2) else None); links=[]; seen=set()
    for el in h.find_all_next():
        if el.name in ('h2','h3') and el is not h and re.match(r'^JBTS Volume\s+\d+',txt(el),re.I):break
        if el.name=='a' and el.get('href'):
            x=(urljoin(ISSUES,el['href']),txt(el))
            if x not in seen:seen.add(x);links.append(x)
    secs[key]=links
expected=[(6,1),(6,2),(7,1),(7,2),(8,1),(9,None),(10,1),(10,2)]
manifest=[]
for vol,iss in expected:
    links=secs.get((vol,iss));
    if links is None:raise SystemExit(f'MISSING SECTION {(vol,iss)}')
    chosen=None
    for href,label in links:
        low=(label+' '+href).lower()
        if 'full issue' in low:
            try:
                u,d=pdf_from(href)
                if d:chosen=(u,d);break
            except Exception as e:print('FULLFAIL',vol,iss,href,repr(e))
    if chosen:
        u,d=chosen; name=(f'Journal of Biblical and Theological Studies - Volume {vol:03d}.pdf' if iss is None else f'Journal of Biblical and Theological Studies - Volume {vol:03d} Issue {iss:02d}.pdf')
        (out/name).write_bytes(d);manifest.append({'volume':vol,'issue':iss,'mode':'official_full_issue','source':u,'file':name,'pages':pages(d),'size':len(d)});print('FULL',vol,iss,pages(d),len(d));continue
    parts=[];meta=[]
    for href,label in links:
        if not label or label.lower().startswith('jbts '):continue
        try:u,d=pdf_from(href)
        except Exception as e:print('PARTFAIL',vol,iss,label[:50],repr(e));continue
        if not d or any(u==x['source'] for x in meta):continue
        parts.append(d);meta.append({'source':u,'title':label,'pages':pages(d),'size':len(d)});print('PART',vol,iss,len(parts),pages(d),label[:70])
    if not parts:raise SystemExit(f'NO PARTS {(vol,iss)}')
    w=PdfWriter()
    for d in parts:
        for p in PdfReader(io.BytesIO(d)).pages:w.add_page(p)
    b=io.BytesIO();w.write(b);d=b.getvalue();name=(f'Journal of Biblical and Theological Studies - Volume {vol:03d} - Reconstructed from official article PDFs.pdf' if iss is None else f'Journal of Biblical and Theological Studies - Volume {vol:03d} Issue {iss:02d} - Reconstructed from official article PDFs.pdf')
    (out/name).write_bytes(d);manifest.append({'volume':vol,'issue':iss,'mode':'reconstructed_official_articles','file':name,'pages':pages(d),'size':len(d),'parts':meta});print('RECON',vol,iss,len(parts),pages(d),len(d))
(out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print('DONE',len(manifest));
if len(manifest)!=8:raise SystemExit('Expected 8 outputs')