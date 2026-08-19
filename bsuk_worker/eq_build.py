import re,json,hashlib,shutil,time
from pathlib import Path
from urllib.parse import urljoin
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests,fitz
from bs4 import BeautifulSoup

BASE='https://biblicalstudies.gospelstudies.org.uk/'
PAGES=['articles_evangelical_quarterly.php']+[f'articles_evangelical_quarterly-{i:02d}.php' for i in range(1,9)]
C=json.load(open('bsuk_worker/eq_corrections.json',encoding='utf-8'))
OUT=Path('eq_build'); CACHE=Path('eq_cache'); OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
UA='Mozilla/5.0 BSUK-Drive-Archiver/0.1 EQ'
clean=lambda s:re.sub(r'\s+',' ',s or '').strip()
norm=lambda s:clean(s).strip(' ,.;')

def title(t):
 m=re.search(r'(?i)\b(?:The\s+)?Evangelical(?:\s+Quarterly)?\s+\d{1,3}\.\d{1,2}\b',t); p=t[:m.start()] if m else t
 a,b=p.find('"'),p.rfind('"')
 return norm(p[a+1:b] if a>=0 and b>a else (p.split(',',1)[1] if ',' in p else p))
def pages(t,v,i):
 m=re.search(rf'(?i)(?:The\s+)?Evangelical(?:\s+Quarterly)?\s+{v}\.{i}\s*\([^)]*\)\s*[:;,]?\s*(\d+)\s*[-–]\s*(\d+)',t)
 if m:return int(m.group(1)),int(m.group(2))
 rs=re.findall(r'(?<!\d)(\d{1,4})\s*[-–]\s*(\d{1,4})(?!\d)',re.split(r'(?i)\bpdf\b',t,1)[0]); return tuple(map(int,rs[-1])) if rs else (None,None)
def pdfhref(h):
 h=(h or '').lower().split('#')[0];return h.endswith('.pdf') or ('/pdf/' in h and '.pdf' in h)
def html(u):
 s=requests.Session();s.headers['User-Agent']=UA
 for n in range(5):
  try:r=s.get(u,timeout=60);r.raise_for_status();return r.text
  except Exception:
   if n==4:raise
   time.sleep(2**n)

years={};rows=[];positions=set()
for p in PAGES:
 pu=BASE+p;s=BeautifulSoup(html(pu),'html.parser')
 for h in s.find_all('h3'):
  m=re.fullmatch(r'Volume\s+(\d+)\s*\(([^)]+)\)',clean(h.get_text(' ',strip=True)),re.I)
  if m:years[int(m.group(1))]=clean(m.group(2))
 for tr in s.find_all('tr'):
  t=clean(tr.get_text(' ',strip=True)); hm=re.fullmatch(r'(\d{1,3})\.(\d{1,2})',t)
  if hm:positions.add(tuple(map(int,hm.groups())));continue
  m=re.search(r'(?i)\b(?:The\s+)?Evangelical(?:\s+Quarterly)?\s+(\d{1,3})\.(\d{1,2})\b',t)
  if not m:continue
  v,i=map(int,m.groups());positions.add((v,i));ttl=title(t);p1,p2=pages(t,v,i)
  links=[urljoin(pu,a['href']) for a in tr.find_all('a',href=True) if pdfhref(a['href'])]
  rows.append({'v':v,'i':i,'y':years.get(v),'t':ttl,'p1':p1,'p2':p2,'links':links})
for r in rows:r['y']=years.get(r['v'])

def key(r):return f"{r['v']}|{r['i']}|{norm(r['t'])}"
def pick(r):
 k=key(r)
 if k in C['row_overrides']:return C['row_overrides'][k]
 for raw in r['links']:
  if raw in C['collision_owners'] and C['collision_owners'][raw]!=k:continue
  return C['bad_url_replacements'].get(raw,raw)
 return None
for r in rows:r['url']=pick(r)
urls=sorted({r['url'] for r in rows if r['url']})

def getpdf(u):
 dst=CACHE/(hashlib.sha256(u.encode()).hexdigest()+'.pdf'); s=requests.Session();s.headers['User-Agent']=UA
 for n in range(5):
  try:
   x=s.get(u,timeout=180);x.raise_for_status();d=x.content
   if not d.startswith(b'%PDF-'):raise RuntimeError('bad PDF header')
   dst.write_bytes(d);z=fitz.open(dst);pc=z.page_count;z.close()
   if pc<1:raise RuntimeError('zero pages')
   return u,str(dst),len(d),hashlib.sha256(d).hexdigest(),pc
  except Exception:
   dst.unlink(missing_ok=True)
   if n==4:raise
   time.sleep(2**n)
cache={}
with ThreadPoolExecutor(max_workers=4) as ex:
 fs={ex.submit(getpdf,u):u for u in urls}
 for n,f in enumerate(as_completed(fs),1):
  u,p,b,h,pc=f.result();cache[u]={'path':p,'bytes':b,'sha256':h,'pages':pc}
  if n%50==0 or n==len(urls):print(f'DOWNLOAD {n}/{len(urls)}',flush=True)

g=defaultdict(list)
for r in rows:g[(r['v'],r['i'])].append(r)
def safe(s):return clean(s).replace('/','-').replace('\\','-').replace('\x00','').rstrip(' .')
outputs=[];gaps=[]
for (v,i),arts in sorted(g.items()):
 arts=sorted(arts,key=lambda r:(r['p1'] if r['p1'] is not None else 99999,r['t']));avail=[r for r in arts if r['url'] in cache]
 if not avail:gaps.append({'v':v,'i':i,'listed':len(arts),'available':0});continue
 vd=OUT/f'Volume {v:03d}';vd.mkdir(exist_ok=True);yr=safe(years.get(v,'Unknown Year'))
 if len(avail)==len(arts):
  fn=f'The Evangelical Quarterly - Volume {v:03d} Issue {i:02d} - {yr} - Reconstructed from official article PDFs.pdf';dst=vd/safe(fn);doc=fitz.open();src=[]
  for r in avail:
   d=fitz.open(cache[r['url']]['path']);doc.insert_pdf(d);d.close();src.append({'title':r['t'],'pages':[r['p1'],r['p2']],'url':r['url'],'sha256':cache[r['url']]['sha256']})
  doc.save(dst,garbage=4,deflate=True);doc.close();chk=fitz.open(dst);pc=chk.page_count;chk.close()
  outputs.append({'v':v,'i':i,'type':'reconstructed','file':str(dst),'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'pdf_pages':pc,'sources':src})
 else:
  gaps.append({'v':v,'i':i,'listed':len(arts),'available':len(avail),'missing':[r['t'] for r in arts if not r['url']]})
  for r in avail:
   pp=f"pp {r['p1']}-{r['p2']}" if r['p1'] is not None else 'pages unknown';fn=f"The Evangelical Quarterly - Volume {v:03d} Issue {i:02d} - {yr} - {r['t']} - {pp}.pdf";dst=vd/safe(fn);shutil.copy2(cache[r['url']]['path'],dst)
   outputs.append({'v':v,'i':i,'type':'article','title':r['t'],'pages':[r['p1'],r['p2']],'file':str(dst),'sha256':cache[r['url']]['sha256'],'source_url':r['url']})
for v,i in sorted(positions):
 if (v,i) not in g:gaps.append({'v':v,'i':i,'listed':0,'available':0,'note':'issue position without article rows'})
shutil.rmtree(CACHE)
M={'target':len(outputs),'reconstructed':sum(x['type']=='reconstructed' for x in outputs),'articles':sum(x['type']=='article' for x in outputs),'outputs':outputs,'gaps':gaps}
(OUT/'build_manifest.json').write_text(json.dumps(M,ensure_ascii=False,indent=2),encoding='utf-8')
print('BUILD_SUMMARY',json.dumps({k:M[k] for k in ['target','reconstructed','articles']},ensure_ascii=False),flush=True)
if M['target']!=523 or M['reconstructed']!=247 or M['articles']!=276:raise SystemExit('Unexpected target/classification; refusing artifact')
