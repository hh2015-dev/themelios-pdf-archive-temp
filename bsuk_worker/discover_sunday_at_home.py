import json,re,hashlib,sys
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

STARTS=[
 'https://biblicalstudies.org.uk/articles_sunday-at-home_01.php',
 'https://biblicalstudies.gospelstudies.org.uk/articles_sunday-at-home_01.php'
]
OUT=Path('out_sunday_at_home'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 BSUK-Archiver/1.0'

def get(url):
 r=S.get(url,timeout=45); r.raise_for_status(); return r

def valid_pdf(b): return len(b)>1000 and b[:5]==b'%PDF-'

# resolve working host
base=None; html=None
for u in STARTS:
 try:
  r=get(u); base=u; html=r.text; break
 except Exception as e: print('START_FAIL',u,repr(e))
if not base: raise SystemExit('No start page reachable')
print('BASE',base)
host=f'{urlparse(base).scheme}://{urlparse(base).netloc}/'

seen=set(); queue=[base]; pages=[]; pdfs=[]; years=set()
while queue:
 u=queue.pop(0)
 if u in seen: continue
 seen.add(u)
 try: text=get(u).text
 except Exception as e:
  pages.append({'url':u,'error':repr(e)}); continue
 soup=BeautifulSoup(text,'html.parser')
 title=soup.title.get_text(' ',strip=True) if soup.title else ''
 page={'url':u,'title':title,'pdf_links':0}
 # capture years/headings
 for tag in soup.find_all(['h2','h3','h4','a']):
  t=' '.join(tag.get_text(' ',strip=True).split())
  for y in re.findall(r'\b(18\d{2}|19\d{2}|20\d{2})\b',t): years.add(int(y))
 for a in soup.find_all('a',href=True):
  href=a['href'].strip(); texta=' '.join(a.get_text(' ',strip=True).split())
  full=urljoin(u,href)
  if re.search(r'articles_sunday-at-home_\d+\.php(?:#.*)?$',full):
   full=full.split('#')[0]
   if full not in seen and full not in queue: queue.append(full)
  if '.pdf' in href.lower():
   pdfs.append({'page':u,'url':full,'label':texta})
   page['pdf_links']+=1
 pages.append(page)

# dedupe exact URLs, preserve first label/page
uniq=[]; by={}
for x in pdfs:
 key=x['url']
 if key not in by: by[key]=x; uniq.append(x)
 else:
  by[key].setdefault('crossrefs',[]).append({'page':x['page'],'label':x['label']})

# download exact linked PDFs
files=[]; errors=[]
for i,x in enumerate(uniq,1):
 try:
  b=get(x['url']).content
  if not valid_pdf(b): raise ValueError(f'not pdf bytes={len(b)} head={b[:20]!r}')
  name=Path(urlparse(x['url']).path).name or f'file_{i:04d}.pdf'
  # avoid collisions
  p=OUT/name
  if p.exists() and p.read_bytes()!=b: p=OUT/f'{i:04d}_{name}'
  p.write_bytes(b)
  files.append({**x,'file':p.name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
  print('OK',i,len(b),x['url'])
 except Exception as e:
  errors.append({**x,'error':repr(e)}); print('ERR',x['url'],repr(e))

manifest={
 'base':base,
 'pages':pages,
 'years':sorted(years),
 'unique_pdf_links':len(uniq),
 'downloaded':len(files),
 'errors':errors,
 'crossref_count':sum(len(x.get('crossrefs',[])) for x in uniq),
 'files':files,
}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
print('SUMMARY',json.dumps({k:manifest[k] for k in ['years','unique_pdf_links','downloaded','crossref_count']},ensure_ascii=False))
print('ERRORS',len(errors))
