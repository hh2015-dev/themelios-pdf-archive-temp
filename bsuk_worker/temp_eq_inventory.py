import json,re,sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

BASE='https://biblicalstudies.gospelstudies.org.uk/'
PAGES=[urljoin(BASE,'articles_evangelical_quarterly.php')]+[urljoin(BASE,f'articles_evangelical_quarterly-{i:02d}.php') for i in range(1,9)]
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 BSUK archival inventory'
CIT=re.compile(r'Evangelical Quarterly\s+(\d+)(?:\.(\d+))?\s*\(([^)]*?(?:18|19|20)\d{2}[^)]*)\)\s*:\s*([0-9ivxlcdm]+(?:\s*[-–]\s*[0-9ivxlcdm]+)?)',re.I)
YEAR=re.compile(r'(18|19|20)\d{2}')

def clean(s): return ' '.join(s.split())
def context(a):
    for p in [a.parent, getattr(a.parent,'parent',None), getattr(getattr(a.parent,'parent',None),'parent',None)]:
        if p:
            t=clean(p.get_text(' ',strip=True))
            if 'Evangelical Quarterly' in t and len(t)<1800:return t
    return clean(a.parent.get_text(' ',strip=True))

def probe(u):
    try:
        r=S.get(u,stream=True,timeout=35,allow_redirects=True,headers={'Range':'bytes=0-15'})
        head=next(r.iter_content(16),b'')[:5]
        return {'url':u,'status':r.status_code,'ctype':r.headers.get('content-type',''),'final_url':r.url,'pdf_magic':head==b'%PDF-','ok':r.status_code in (200,206) and head==b'%PDF-'}
    except Exception as e:return {'url':u,'status':None,'ctype':'','final_url':'','pdf_magic':False,'ok':False,'error':repr(e)}

all_cits=[]; pdfs=[]; page_results=[]
for u in PAGES:
    r=S.get(u,timeout=45); page_results.append({'url':u,'status':r.status_code,'bytes':len(r.content)})
    r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser'); text=clean(soup.get_text(' ',strip=True))
    for m in CIT.finditer(text):
        y=YEAR.search(m.group(3)); all_cits.append({'volume':int(m.group(1)),'issue':int(m.group(2)) if m.group(2) else None,'date':m.group(3),'year':int(y.group()) if y else None,'pages':clean(m.group(4)),'page_url':u})
    for a in soup.find_all('a',href=True):
        href=a['href']
        if '.pdf' not in href.lower(): continue
        absu=urljoin(u,href); c=context(a); m=CIT.search(c); y=YEAR.search(m.group(3)) if m else None
        pdfs.append({'url':absu,'host':urlparse(absu).netloc.lower(),'context':c,'volume':int(m.group(1)) if m else None,'issue':int(m.group(2)) if m and m.group(2) else None,'date':m.group(3) if m else None,'year':int(y.group()) if y else None,'pages':clean(m.group(4)) if m else None,'page_url':u})
# Dedupe PDF URLs while preserving metadata
uniq={}
for x in pdfs: uniq.setdefault(x['url'],x)
pdfs=list(uniq.values())
with ThreadPoolExecutor(max_workers=4) as ex:
    fut={ex.submit(probe,x['url']):x for x in pdfs}
    for f in as_completed(fut): fut[f]['probe']=f.result()
# citation occurrences can repeat because nav/HTML; dedupe bibliographic tuple
citkeys={}
for x in all_cits: citkeys.setdefault((x['volume'],x['issue'],x['year'],x['pages']),x)
cits=list(citkeys.values())
vols=sorted({x['volume'] for x in cits if x['volume']})
issues=sorted({(x['volume'],x['issue']) for x in cits if x['volume'] and x['issue']})
years=sorted({x['year'] for x in cits if x['year']})
summary={'pages':page_results,'volume_count':len(vols),'volumes':vols,'year_min':min(years) if years else None,'year_max':max(years) if years else None,'issue_count':len(issues),'issues_by_volume':{str(v):sorted({i for vv,i in issues if vv==v}) for v in vols},'article_citation_count':len(cits),'pdf_link_count':len(pdfs),'working_pdf_count':sum(x['probe']['ok'] for x in pdfs),'broken_pdf_count':sum(not x['probe']['ok'] for x in pdfs),'hosts':dict(Counter(x['host'] for x in pdfs)),'unparsed_pdf_count':sum(x['volume'] is None for x in pdfs)}
open('eq_summary.json','w',encoding='utf8').write(json.dumps(summary,ensure_ascii=False,indent=2))
with open('eq_manifest.jsonl','w',encoding='utf8') as f:
    for x in sorted(pdfs,key=lambda z:(z['volume'] or 999,z['issue'] or 99,z['pages'] or'',z['url'])): f.write(json.dumps(x,ensure_ascii=False)+'\n')
print('EQ_SUMMARY='+json.dumps(summary,ensure_ascii=False,separators=(',',':')))
for x in pdfs:
    if not x['probe']['ok']: print('BROKEN='+json.dumps(x,ensure_ascii=False,separators=(',',':')))
