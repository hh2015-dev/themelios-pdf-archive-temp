from __future__ import annotations
import hashlib,re,json
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

OUT=Path('whs_corpus'); OUT.mkdir(exist_ok=True)
BASE='https://biblicalstudies.gospelstudies.org.uk/articles_whs_{:02d}.php'
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 BSUK academic archive/1.0'})
urls={}
for pi in range(1,14):
 r=s.get(BASE.format(pi),timeout=30); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser'); vol=0
 for node in soup.find_all(['h1','h2','h3','h4','a']):
  if node.name in ('h1','h2','h3','h4'):
   m=re.search(r'\bVolume\s+(\d+)\b',' '.join(node.stripped_strings),re.I)
   if m: vol=int(m.group(1))
   continue
  href=(node.get('href') or '').strip(); txt=' '.join(node.stripped_strings)
  if not href: continue
  if '.pdf' not in (href+' '+txt).lower(): continue
  u=urljoin(BASE.format(pi),href)
  if '/pdf/whs/' not in u: continue
  urls.setdefault(u,{'vol':vol,'anchor':txt})
print('TARGET_URLS',len(urls),flush=True)
assert len(urls)==453, len(urls)
manifest=[]; seen_sha={}
for i,(u,meta) in enumerate(urls.items(),1):
 vol=meta['vol']; fn=u.rsplit('/',1)[-1]
 dest=(OUT/(f'Volume_{vol:03d}' if vol else 'Journal_Root')); dest.mkdir(exist_ok=True)
 p=dest/fn
 with s.get(u,timeout=120,stream=True,allow_redirects=True) as r:
  r.raise_for_status(); h=hashlib.sha256(); size=0; first=b''
  with p.open('wb') as f:
   for ch in r.iter_content(1024*1024):
    if not ch: continue
    if len(first)<8: first=(first+ch)[:8]
    f.write(ch); h.update(ch); size+=len(ch)
 sha=h.hexdigest(); assert first.startswith(b'%PDF-') and size>=1024,(u,first,size)
 assert sha not in seen_sha,(u,seen_sha.get(sha)); seen_sha[sha]=u
 manifest.append({'volume':vol,'url':u,'source_name':fn,'size':size,'sha256':sha,'anchor':meta['anchor']})
 print(f'FETCH {i}/453 V{vol:03d} {fn} {size} {sha}',flush=True)
(OUT/'_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('FETCH_COMPLETE',len(manifest),sum(x['size'] for x in manifest),flush=True)
