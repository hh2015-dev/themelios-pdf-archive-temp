import re, json, requests
from bs4 import BeautifulSoup

BASE='https://biblicalstudies.gospelstudies.org.uk/'
PAGES=['articles_evangelical_quarterly.php']+[f'articles_evangelical_quarterly-{i:02d}.php' for i in range(1,9)]
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 BSUK-EQ-Inventory/1.0'

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
for page in PAGES:
    url=BASE+page
    r=S.get(url,timeout=60); print('PAGE',page,'HTTP',r.status_code,'CTYPE',r.headers.get('content-type'),'BYTES',len(r.content),flush=True); r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    print('TITLE',clean(soup.title.get_text(' ',strip=True) if soup.title else ''))
    for tag in ['table','tr','td','p','h1','h2','h3','h4','a']:
        print('COUNT',tag,len(soup.find_all(tag)))
    candidates=[]
    for el in soup.find_all(['tr','p','h1','h2','h3','h4','div','li']):
        txt=clean(el.get_text(' ',strip=True))
        if not txt: continue
        if re.search(r'\bVolume\s+\d+\b',txt,re.I) or re.search(r'\b\d{1,2}\.\d{1,2}\b',txt) or ('pp.' in txt and len(txt)<1000):
            links=[{'text':clean(a.get_text(' ',strip=True)),'href':a.get('href')} for a in el.find_all('a',href=True)]
            candidates.append({'tag':el.name,'text':txt[:600],'links':links[:8]})
    print('CANDIDATES',len(candidates))
    for x in candidates[:50]: print('CAND',json.dumps(x,ensure_ascii=False),flush=True)
    print('---ENDPAGE---',flush=True)
