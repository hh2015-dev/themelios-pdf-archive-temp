import requests, re, json, hashlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin
BASE='https://biblicalstudies.org.uk/'
pages=['articles_sword-and-the-trowel_01.php','articles_sword-and-the-trowel_02.php']
out={'pages':[],'pdfs':[],'errors':[]}
s=requests.Session(); s.headers['User-Agent']='Mozilla/5.0'
seen=set()
for p in pages:
    u=urljoin(BASE,p)
    try:
        r=s.get(u,timeout=30); r.raise_for_status()
    except Exception as e:
        out['errors'].append({'page':u,'error':str(e)}); continue
    soup=BeautifulSoup(r.text,'html.parser')
    links=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(u,a['href'])
        if href.lower().endswith('.pdf') and 'sword-and-the-trowel' in href.lower():
            links.append({'url':href,'text':' '.join(a.stripped_strings)})
            if href not in seen:
                seen.add(href); out['pdfs'].append({'url':href,'text':' '.join(a.stripped_strings)})
    years=sorted(set(int(x) for x in re.findall(r'\b(18\d{2}|190[0-4])\b',soup.get_text(' ',strip=True))))
    out['pages'].append({'url':u,'status':r.status_code,'years':years,'pdf_count':len(links)})
# Probe canonical annual complete volumes, which the index points to.
annual=[]
for y in range(1865,1905):
    u=f'{BASE}pdf/sword-and-the-trowel/sword-and-the-trowel_{y}.pdf'
    try:
        r=s.get(u,timeout=60)
        ok=r.status_code==200 and r.content.startswith(b'%PDF')
        annual.append({'year':y,'url':u,'status':r.status_code,'ok':ok,'bytes':len(r.content) if ok else None,'sha256':hashlib.sha256(r.content).hexdigest() if ok else None})
    except Exception as e:
        annual.append({'year':y,'url':u,'ok':False,'error':str(e)})
out['annual']=annual
out['summary']={'index_unique_pdfs':len(out['pdfs']),'annual_ok':sum(1 for x in annual if x.get('ok')),'annual_missing':[x['year'] for x in annual if not x.get('ok')]}
open('sword_trowel_audit.json','w',encoding='utf-8').write(json.dumps(out,indent=2,ensure_ascii=False))
print(json.dumps(out['summary'],indent=2))
