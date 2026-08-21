import os,re,json,hashlib
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

PAGES=[f'https://biblicalstudies.gospelstudies.org.uk/articles_tsfbulletin_0{i}.php' for i in range(1,5)]
OUT='tsfbulletin_uk_stage'
TITLE='Theological Students Fellowship Bulletin'
os.makedirs(OUT,exist_ok=True)
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0'})

manifest={'title':TITLE,'pages':PAGES,'volumes':{},'files':[],'errors':[],'crossrefs':[]}
seen={}
for page in PAGES:
    r=s.get(page,timeout=60); r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    current_vol=None
    for tag in soup.find_all(['h3','a']):
        if tag.name=='h3':
            txt=' '.join(tag.stripped_strings)
            m=re.search(r'Volume\s+(\d+)',txt,re.I)
            if m:
                current_vol=int(m.group(1))
                manifest['volumes'].setdefault(str(current_vol),{'heading':txt,'linked_pdfs':0,'unique_pdfs':0})
        elif tag.name=='a' and current_vol and tag.get('href'):
            href=tag['href']
            label=' '.join(tag.stripped_strings)
            if '.pdf' not in href.lower() and ' pdf' not in label.lower():
                continue
            url=urljoin(page,href)
            if not url.lower().split('?')[0].endswith('.pdf'):
                continue
            manifest['volumes'][str(current_vol)]['linked_pdfs']+=1
            if url in seen:
                manifest['crossrefs'].append({'volume':current_vol,'url':url,'first_volume':seen[url],'label':label})
                continue
            seen[url]=current_vol
            base=os.path.basename(urlparse(url).path) or f'volume_{current_vol:03d}.pdf'
            folder=os.path.join(OUT,f'Volume {current_vol:03d}')
            os.makedirs(folder,exist_ok=True)
            path=os.path.join(folder,base)
            try:
                rr=s.get(url,timeout=120,allow_redirects=True); rr.raise_for_status(); data=rr.content
                if not data.startswith(b'%PDF'):
                    raise RuntimeError(f'not PDF: {rr.status_code} {rr.headers.get("content-type")} {len(data)}')
                with open(path,'wb') as f: f.write(data)
                rec={'volume':current_vol,'label':label,'url':url,'file':base,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                manifest['files'].append(rec)
                manifest['volumes'][str(current_vol)]['unique_pdfs']+=1
                print('OK',current_vol,base,len(data))
            except Exception as e:
                manifest['errors'].append({'volume':current_vol,'label':label,'url':url,'error':str(e)})
                print('ERR',current_vol,url,e)

with open(os.path.join(OUT,'manifest.json'),'w',encoding='utf-8') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'manifest.txt'),'w',encoding='utf-8') as f:
    f.write(f"VOLUMES={len(manifest['volumes'])}\nUNIQUE_PDFS={len(manifest['files'])}\nERRORS={len(manifest['errors'])}\nCROSSREFS={len(manifest['crossrefs'])}\n")
    for v in range(1,73):
        z=manifest['volumes'].get(str(v),{})
        f.write(f"V{v:03d}\tlinked={z.get('linked_pdfs',0)}\tunique={z.get('unique_pdfs',0)}\t{z.get('heading','')}\n")
    f.write('\nFILES\n')
    for z in manifest['files']:
        f.write(f"V{z['volume']:03d}\t{z['bytes']}\t{z['file']}\t{z['url']}\n")
    if manifest['errors']:
        f.write('\nERRORS\n')
        for e in manifest['errors']: f.write(json.dumps(e,ensure_ascii=False)+'\n')
print(json.dumps({'volumes':len(manifest['volumes']),'unique_pdfs':len(manifest['files']),'errors':len(manifest['errors']),'crossrefs':len(manifest['crossrefs'])},indent=2))
