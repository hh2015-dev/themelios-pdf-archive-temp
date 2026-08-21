# run trigger 2026-08-21
import os, re, json, hashlib
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

PAGE='https://biblicalstudies.org.uk/articles_tsfbulletin-us.php'
OUT='tsf_stage'
TITLE='Theological Students Fellowship Bulletin (US)'
os.makedirs(OUT, exist_ok=True)

s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0'})
r=s.get(PAGE,timeout=60); r.raise_for_status()
soup=BeautifulSoup(r.text,'html.parser')

items=[]
current_vol=None
current_issue=None
current_year=None
for tag in soup.find_all(['h2','h3','a']):
    if tag.name=='h2':
        txt=' '.join(tag.stripped_strings)
        m=re.search(r'Vol\.\s*(\d+)\s*\(([^)]+)\)',txt,re.I)
        if m:
            current_vol=int(m.group(1)); current_year=m.group(2).strip(); current_issue=None
    elif tag.name=='h3':
        txt=' '.join(tag.stripped_strings).strip()
        if txt and 'Download Complete Issue pdf' not in txt:
            current_issue=txt
    elif tag.name=='a':
        txt=' '.join(tag.stripped_strings)
        if 'Download Complete Issue pdf' in txt and tag.get('href') and current_vol:
            url=urljoin(PAGE,tag['href'])
            items.append({'volume':current_vol,'year':current_year,'issue_label':current_issue,'url':url})

seen=set(); clean=[]
for x in items:
    if x['url'] in seen: continue
    seen.add(x['url']); clean.append(x)
items=clean

counts={}
manifest={'source_page':PAGE,'title':TITLE,'issues':[],'errors':[]}
for x in items:
    v=x['volume']; counts[v]=counts.get(v,0)+1; n=counts[v]
    name=f'{TITLE} - Volume {v:03d} Issue {n:02d}.pdf'
    path=os.path.join(OUT,name)
    try:
        rr=s.get(x['url'],timeout=120,allow_redirects=True); rr.raise_for_status(); data=rr.content
        if not data.startswith(b'%PDF'):
            raise RuntimeError(f'not PDF: {rr.status_code} {rr.headers.get("content-type")} {len(data)} bytes')
        open(path,'wb').write(data)
        manifest['issues'].append({**x,'issue_number':n,'file':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'valid_pdf':True})
        print('OK',v,n,x['issue_label'],len(data),x['url'])
    except Exception as e:
        manifest['errors'].append({**x,'issue_number':n,'file':name,'error':str(e)})
        print('ERR',v,n,x['url'],e)

manifest['independent_indexes']=[]
for a in soup.find_all('a',href=True):
    label=' '.join(a.stripped_strings)
    low=label.lower()
    if any(k in low for k in ['index','cumulative index','bibliography']) and a['href'].lower().endswith('.pdf'):
        manifest['independent_indexes'].append({'label':label,'url':urljoin(PAGE,a['href'])})

with open(os.path.join(OUT,'manifest.json'),'w',encoding='utf-8') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'manifest.txt'),'w',encoding='utf-8') as f:
    f.write(f"TITLE={TITLE}\nSOURCE={PAGE}\nISSUES={len(manifest['issues'])}\nERRORS={len(manifest['errors'])}\nINDEX_PDFS={len(manifest['independent_indexes'])}\n")
    for v in sorted(counts):
        ok=sum(1 for z in manifest['issues'] if z['volume']==v)
        f.write(f"VOLUME {v:03d}: {ok} issues\n")
    f.write('\n')
    for z in manifest['issues']:
        f.write(f"V{z['volume']:03d} I{z['issue_number']:02d}\t{z['year']}\t{z['issue_label']}\t{z['bytes']}\t{z['file']}\t{z['url']}\n")
    if manifest['errors']:
        f.write('\nERRORS\n')
        for e in manifest['errors']: f.write(json.dumps(e,ensure_ascii=False)+'\n')
print(json.dumps({'issues':len(manifest['issues']),'errors':len(manifest['errors']),'counts':counts,'indexes':len(manifest['independent_indexes'])},indent=2))
