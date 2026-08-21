# TBHS archive run trigger 2026-08-21
import os, re, json, hashlib, sys
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE = 'https://biblicalstudies.org.uk/'
START = 'https://biblicalstudies.org.uk/articles_tbhs_01.php'
OUT = 'tbhs_stage'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'}

os.makedirs(OUT, exist_ok=True)
s = requests.Session(); s.headers.update(UA)

pages=[]
for i in range(1, 10):
    url=f'https://biblicalstudies.org.uk/articles_tbhs_{i:02d}.php'
    r=s.get(url, timeout=45, allow_redirects=True)
    if r.status_code != 200 or len(r.content) < 1000:
        if i == 1:
            raise RuntimeError(f'Failed start page {url}: {r.status_code}')
        break
    txt=r.text
    if 'Transactions of the Baptist Historical Society' not in txt and 'Baptist Historical Society' not in txt:
        break
    pages.append((url,txt))

records=[]
for page_url, html in pages:
    soup=BeautifulSoup(html,'html.parser')
    for a in soup.find_all('a', href=True):
        href=urljoin(page_url,a['href'])
        label=' '.join(a.stripped_strings)
        low=(href+' '+label).lower()
        if not href.lower().endswith('.pdf'):
            continue
        parsed=urlparse(href)
        if 'biblicalstudies.org.uk' not in parsed.netloc:
            kind='external_pdf'
        elif '/pdf/tbhs/volumes/' in parsed.path.lower():
            kind='complete_issue_or_volume_pdf'
        elif any(k in low for k in ['index','contents','bibliograph']):
            kind='index_or_contents_pdf'
        else:
            kind='article_pdf'
        records.append({'page':page_url,'label':label,'url':href,'kind':kind})

uniq=[]; seen=set()
for x in records:
    if x['url'] in seen: continue
    seen.add(x['url']); uniq.append(x)
records=uniq
selected=[x for x in records if x['kind'] in ('complete_issue_or_volume_pdf','index_or_contents_pdf','external_pdf')]
manifest={'pages':[p[0] for p in pages], 'all_pdf_links':records, 'selected':[], 'errors':[]}

for rec in selected:
    url=rec['url']
    fn=os.path.basename(urlparse(url).path) or 'download.pdf'
    dest=os.path.join(OUT,fn)
    try:
        rr=s.get(url,timeout=90,allow_redirects=True)
        rr.raise_for_status()
        data=rr.content
        if not data.startswith(b'%PDF'):
            raise ValueError(f'not PDF: status={rr.status_code} type={rr.headers.get("content-type")} size={len(data)}')
        with open(dest,'wb') as f: f.write(data)
        rec2=dict(rec)
        rec2.update({'file':fn,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'valid_pdf':True})
        m=re.match(r'(?P<vol>\d{2})-(?P<issue>\d(?:_\d)?)\.pdf$',fn,re.I)
        if m:
            rec2['volume']=int(m.group('vol'))
            rec2['issue_token']=m.group('issue')
        manifest['selected'].append(rec2)
        print('OK',fn,len(data),url)
    except Exception as e:
        manifest['errors'].append({'url':url,'file':fn,'error':str(e)})
        print('ERR',url,e,file=sys.stderr)

with open(os.path.join(OUT,'manifest.json'),'w',encoding='utf-8') as f:
    json.dump(manifest,f,ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'manifest.txt'),'w',encoding='utf-8') as f:
    f.write('PAGES\n'+'\n'.join(manifest['pages'])+'\n\n')
    f.write(f"ALL_PDF_LINKS={len(records)}\nSELECTED={len(manifest['selected'])}\nERRORS={len(manifest['errors'])}\n\n")
    for x in manifest['selected']:
        f.write(f"{x.get('volume','?')}\t{x.get('issue_token','?')}\t{x['file']}\t{x['bytes']}\t{x['sha256']}\t{x['url']}\n")
    if manifest['errors']:
        f.write('\nERRORS\n')
        for e in manifest['errors']:
            f.write(json.dumps(e,ensure_ascii=False)+'\n')

print(json.dumps({'pages':manifest['pages'],'selected':len(manifest['selected']),'errors':len(manifest['errors'])},indent=2))
