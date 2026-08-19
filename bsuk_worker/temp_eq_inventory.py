import json,re
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

BASE='https://biblicalstudies.gospelstudies.org.uk/'
PAGES=[urljoin(BASE,'articles_evangelical_quarterly.php')]+[urljoin(BASE,f'articles_evangelical_quarterly-{i:02d}.php') for i in range(1,9)]
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 BSUK archival inventory'
CIT=re.compile(r'Evangelical Quarterly\s+(\d+)\.(\d+)\s*\(([^)]*?(?:18|19|20)\d{2}[^)]*)\)\s*:\s*([0-9ivxlcdm]+(?:\s*[-–]\s*[0-9ivxlcdm]+)?)',re.I)
VOLHEAD=re.compile(r'^Volume\s+(\d+)\s*\(([^)]*)\)',re.I)
ISSHEAD=re.compile(r'^(\d+)\.(\d+)$')
YEAR=re.compile(r'(?:18|19|20)\d{2}')

def clean(s): return ' '.join(str(s).split())
def title_from(s):
    m=re.search(r'["“](.+?)["”]\s*,?\s*(?:The\s+)?Evangelical Quarterly',s,re.I)
    return clean(m.group(1)) if m else None

def probe(u):
    try:
        r=S.get(u,stream=True,timeout=35,allow_redirects=True,headers={'Range':'bytes=0-15'})
        head=next(r.iter_content(16),b'')[:5]
        return {'status':r.status_code,'ctype':r.headers.get('content-type',''),'final_url':r.url,'pdf_magic':head==b'%PDF-','ok':r.status_code in (200,206) and head==b'%PDF-'}
    except Exception as e:return {'status':None,'ctype':'','final_url':'','pdf_magic':False,'ok':False,'error':repr(e)}

pdfs=[]; pages=[]; headings=[]; article_rows=[]
for u in PAGES:
    r=S.get(u,timeout=45); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
    pages.append({'url':u,'status':r.status_code,'bytes':len(r.content)})
    strings=[clean(x) for x in soup.stripped_strings]
    current_vol=None
    for s in strings:
        vm=VOLHEAD.match(s)
        if vm: current_vol=int(vm.group(1)); headings.append({'type':'volume','volume':current_vol,'label':s,'page_url':u}); continue
        im=ISSHEAD.match(s)
        if im: headings.append({'type':'issue','volume':int(im.group(1)),'issue':int(im.group(2)),'label':s,'page_url':u})
    # Count listed bibliographic records from citation occurrences in rendered text; page has one citation per listed article.
    flat=clean(soup.get_text(' ',strip=True))
    for m in CIT.finditer(flat):
        y=YEAR.search(m.group(3)); article_rows.append((m.group(1),m.group(2),y.group() if y else '',clean(m.group(4))))
    for a in soup.find_all('a',href=True):
        href=a['href']
        if '.pdf' not in href.lower(): continue
        absu=urljoin(u,href)
        # Headings are authoritative for volume/issue because some citations on the site have typographical volume numbers.
        prev_issue=a.find_previous(string=lambda x: bool(x and ISSHEAD.match(clean(x))))
        hm=ISSHEAD.match(clean(prev_issue)) if prev_issue else None
        vol=int(hm.group(1)) if hm else None; issue=int(hm.group(2)) if hm else None
        txt=clean(a.get_text(' ',strip=True)); c=txt
        if 'Evangelical Quarterly' not in c:
            p=a.parent
            for _ in range(4):
                if not p: break
                t=clean(p.get_text(' ',strip=True))
                if 'Evangelical Quarterly' in t: c=t; break
                p=p.parent
        cm=CIT.search(c); y=YEAR.search(cm.group(3)) if cm else None
        pdfs.append({'url':absu,'host':urlparse(absu).netloc.lower(),'volume':vol,'issue':issue,'title':title_from(c),'year':int(y.group()) if y else None,'date':cm.group(3) if cm else None,'pages':clean(cm.group(4)) if cm else None,'context':c,'page_url':u})
uniq={}
for x in pdfs: uniq.setdefault(x['url'],x)
pdfs=list(uniq.values())
with ThreadPoolExecutor(max_workers=4) as ex:
    fs={ex.submit(probe,x['url']):x for x in pdfs}
    for f in as_completed(fs): fs[f]['probe']=f.result()
volheads={h['volume']:h for h in headings if h['type']=='volume'}
issues=sorted({(h['volume'],h['issue']) for h in headings if h['type']=='issue'})
# Deduplicate article citations by citation identity; independent of issue headings.
article_count=len(set(article_rows))
pdf_by_vol=Counter(x['volume'] for x in pdfs if x['probe']['ok'] and x['volume'])
pdf_by_issue=Counter(f"{x['volume']}.{x['issue']}" for x in pdfs if x['probe']['ok'] and x['volume'] and x['issue'])
yrs=[]
for h in volheads.values(): yrs += [int(y) for y in YEAR.findall(h['label'])]
summary={'pages':pages,'volume_count':len(volheads),'volumes':sorted(volheads),'volume_labels':{str(k):v['label'] for k,v in sorted(volheads.items())},'year_min':min(yrs) if yrs else None,'year_max':max(yrs) if yrs else None,'issue_position_count':len(issues),'issues_by_volume':{str(v):sorted(i for vv,i in issues if vv==v) for v in sorted(volheads)},'article_citation_count':article_count,'pdf_link_count':len(pdfs),'working_pdf_count':sum(x['probe']['ok'] for x in pdfs),'broken_pdf_count':sum(not x['probe']['ok'] for x in pdfs),'hosts':dict(Counter(x['host'] for x in pdfs)),'working_pdf_by_volume':dict(sorted(pdf_by_vol.items())),'working_pdf_by_issue':dict(sorted(pdf_by_issue.items())),'volumes_with_working_pdf':sorted(pdf_by_vol),'unparsed_title_count':sum(not x['title'] for x in pdfs),'unparsed_heading_count':sum(not x['volume'] or not x['issue'] for x in pdfs)}
open('eq_summary.json','w',encoding='utf8').write(json.dumps(summary,ensure_ascii=False,indent=2))
with open('eq_manifest.jsonl','w',encoding='utf8') as f:
    for x in sorted(pdfs,key=lambda z:(z['volume'] or 999,z['issue'] or 99,z['pages'] or'',z['url'])): f.write(json.dumps(x,ensure_ascii=False)+'\n')
print('EQ_SUMMARY='+json.dumps(summary,ensure_ascii=False,separators=(',',':')))
for x in pdfs:
    if not x['probe']['ok']: print('BROKEN='+json.dumps(x,ensure_ascii=False,separators=(',',':')))
