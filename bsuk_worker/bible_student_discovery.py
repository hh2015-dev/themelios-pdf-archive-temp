from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from pathlib import Path
import csv, json, re, requests, time

BASE = 'https://www.biblicalstudies.org.uk/'
PAGES = [urljoin(BASE, f'articles_bible-student_{n:02d}.php') for n in range(1,5)]
OUT = Path('bible_student_discovery')
OUT.mkdir(exist_ok=True)
HEADERS = {'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'}

session = requests.Session(); session.headers.update(HEADERS)
links=[]; page_results=[]

for page in PAGES:
    try:
        r=session.get(page, timeout=60)
        status=r.status_code
        html=r.text if r.ok else ''
        title=''
        if html:
            soup=BeautifulSoup(html,'html.parser')
            title=soup.title.get_text(' ',strip=True) if soup.title else ''
            (OUT/(Path(urlparse(page).path).name+'.html')).write_text(html,encoding='utf-8')
            for a in soup.find_all('a',href=True):
                href=a.get('href','').strip()
                resolved=urljoin(page,href)
                low=resolved.lower()
                if '/pdf/bible-student/' not in low and not ('.pdf' in low and 'bible-student' in low):
                    continue
                parent=a.find_parent(['tr','li','p','div','td'])
                context=' '.join(parent.stripped_strings) if parent else ' '.join(a.stripped_strings)
                context=re.sub(r'\s+',' ',context).strip()
                m=re.search(r'bible-student_(\d+)-(\d+)_',resolved,re.I)
                vol=int(m.group(1)) if m else None
                issue=int(m.group(2)) if m else None
                links.append({'source_page':page,'url':resolved,'raw_href':href,'context':context,'volume':vol,'issue':issue})
        page_results.append({'page':page,'status':status,'bytes':len(r.content),'title':title})
        print('PAGE',page,status,len(r.content),title)
    except Exception as e:
        page_results.append({'page':page,'status':'ERROR','bytes':0,'title':'','error':repr(e)})
        print('PAGE_ERROR',page,repr(e))

# URL-level dedupe while preserving first source context.
uniq=[]; seen=set()
for x in links:
    if x['url'] in seen: continue
    seen.add(x['url']); uniq.append(x)
links=uniq

def probe(item):
    url=item['url']
    last=None
    for attempt in range(3):
        try:
            rr=requests.get(url,headers={**HEADERS,'Range':'bytes=0-31'},stream=True,timeout=45,allow_redirects=True)
            first=b''
            for chunk in rr.iter_content(32):
                if chunk:
                    first+=chunk
                    if len(first)>=8: break
            rr.close()
            return {'status':rr.status_code,'final_url':rr.url,'pdf_magic':first.startswith(b'%PDF-'),'content_type':rr.headers.get('Content-Type',''),'first_hex':first[:8].hex()}
        except Exception as e:
            last=repr(e); time.sleep(1+attempt)
    return {'status':'ERROR','final_url':url,'pdf_magic':False,'content_type':'','first_hex':'','error':last}

with ThreadPoolExecutor(max_workers=4) as ex:
    futs={ex.submit(probe,x):i for i,x in enumerate(links)}
    for fut in as_completed(futs):
        i=futs[fut]; links[i].update(fut.result())

# Summaries.
domains=Counter(urlparse(x['url']).netloc for x in links)
by_volume=defaultdict(lambda:{'links':0,'issues':set(),'valid_pdf':0,'bad':0})
for x in links:
    v=x['volume']
    if v is None: continue
    d=by_volume[v]; d['links']+=1
    if x['issue'] is not None: d['issues'].add(x['issue'])
    if x.get('pdf_magic'): d['valid_pdf']+=1
    else: d['bad']+=1

vol_summary={str(v):{'links':d['links'],'issues':sorted(d['issues']),'valid_pdf':d['valid_pdf'],'bad':d['bad']} for v,d in sorted(by_volume.items())}
summary={
    'pages':page_results,
    'unique_pdf_links':len(links),
    'valid_pdf_magic':sum(1 for x in links if x.get('pdf_magic')),
    'broken_or_non_pdf':sum(1 for x in links if not x.get('pdf_magic')),
    'domains':dict(domains),
    'volumes':vol_summary,
    'volumes_with_links':sorted(by_volume),
    'issue_positions':sum(len(d['issues']) for d in by_volume.values()),
}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:
    fields=['source_page','volume','issue','url','status','pdf_magic','content_type','final_url','context','raw_href','first_hex']
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(links)
print(json.dumps(summary,ensure_ascii=False,indent=2))
