import csv, json, re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE='https://biblicalstudies.gospelstudies.org.uk/'
PAGES=['articles_evangelical_quarterly.php',*[f'articles_evangelical_quarterly-{i:02d}.php' for i in range(1,9)]]
UA={'User-Agent':'Mozilla/5.0 BSUK-EQ-Inventory/2.0'}
CIT_RE=re.compile(r'(?:The\s+)?Evangelical Quarterly\s+(\d{1,2})[\.:](\d)',re.I)
ISSUE_RE=re.compile(r'^\s*(\d{1,2})\.(\d)\s*$')
VOL_RE=re.compile(r'Volume\s+(\d{1,2})\s*\(([^)]*)\)',re.I)
YEAR_RE=re.compile(r'\(([^)]*(?:19|20)\d{2}[^)]*)\)')
PAGE_RE=re.compile(r':\s*(\d{1,4}(?:\s*[-–]\s*\d{1,4})?)\.?\s*(?:pdf|Article in Journal|$)',re.I)
TITLE_RE=re.compile(r'[“"]([^”"]+)[”"]')
S=requests.Session(); S.headers.update(UA)
volumes={}; issues=set(); article_rows=[]; pdf_occ=[]; page_stats=[]

def parse_row(tr,page):
    text=' '.join(tr.stripped_strings)
    cm=CIT_RE.search(text)
    vol=iss=None
    if cm: vol,iss=int(cm.group(1)),int(cm.group(2)); issues.add((vol,iss))
    ym=YEAR_RE.search(text); year=ym.group(1).strip() if ym else ''
    tm=TITLE_RE.search(text); title=tm.group(1).strip() if tm else ''
    pm=PAGE_RE.search(text); pages=pm.group(1).replace('–','-').replace(' ','') if pm else ''
    return {'volume':vol,'issue':iss,'year_text':year,'pages':pages,'title':title,'text':text,'page':page}

for page in PAGES:
    url=urljoin(BASE,page); r=S.get(url,timeout=30); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
    for s in soup.stripped_strings:
        im=ISSUE_RE.match(s)
        if im: issues.add((int(im.group(1)),int(im.group(2))))
        vm=VOL_RE.search(s)
        if vm: volumes[int(vm.group(1))]=vm.group(2).strip()
    rows=0; links=0
    for tr in soup.find_all('tr'):
        meta=parse_row(tr,page)
        if meta['volume'] is not None:
            article_rows.append(meta); rows+=1
        for a in tr.find_all('a',href=True):
            href=urljoin(url,a['href']); label=a.get_text(' ',strip=True).lower()
            if '.pdf' in href.lower() or 'pdf' in label:
                pdf_occ.append({**meta,'url':href,'anchor_text':a.get_text(' ',strip=True)}); links+=1
    page_stats.append({'page':page,'article_rows':rows,'pdf_link_occurrences':links})

# Dedup articles by source row bibliographic citation; keep malformed but distinct rows.
uniq_articles={}
for a in article_rows:
    k=(a['volume'],a['issue'],a['year_text'],a['pages'],a['title'],a['text'])
    uniq_articles.setdefault(k,a)
article_rows=list(uniq_articles.values())
unique_urls=sorted(set(p['url'] for p in pdf_occ))

def check(u):
    out={'url':u,'ok':False,'status':None,'content_type':'','final_url':'','host':urlparse(u).netloc.lower(),'pdf_header':False,'error':''}
    try:
        rr=requests.get(u,headers={**UA,'Range':'bytes=0-31'},stream=True,timeout=25,allow_redirects=True)
        out['status']=rr.status_code; out['content_type']=rr.headers.get('content-type',''); out['final_url']=rr.url; out['host']=urlparse(rr.url).netloc.lower()
        b=next(rr.iter_content(32),b''); rr.close(); out['pdf_header']=b.startswith(b'%PDF-'); out['ok']=200<=out['status']<400 and out['pdf_header']
    except Exception as e: out['error']=repr(e)
    return out
checks=[]
with ThreadPoolExecutor(max_workers=4) as ex:
    fs={ex.submit(check,u):u for u in unique_urls}
    for n,f in enumerate(as_completed(fs),1):
        checks.append(f.result())
        if n%100==0 or n==len(fs): print(f'CHECKED {n}/{len(fs)}',flush=True)
cb={c['url']:c for c in checks}
for p in pdf_occ: p['validation']=cb[p['url']]
vol_issues=defaultdict(list)
for v,i in sorted(issues): vol_issues[v].append(i)
vol_pdf=Counter(p['volume'] for p in pdf_occ if p['volume'] is not None)
vol_articles=Counter(a['volume'] for a in article_rows if a['volume'] is not None)
host_occ=Counter((cb[p['url']].get('host') or urlparse(p['url']).netloc.lower()) for p in pdf_occ)
host_unique=Counter((c.get('host') or urlparse(c['url']).netloc.lower()) for c in checks)
dups={u:sum(1 for p in pdf_occ if p['url']==u) for u in unique_urls}; dups={u:n for u,n in dups.items() if n>1}
unmapped=[p for p in pdf_occ if p['volume'] is None or p['issue'] is None]
summary={
 'year_range':[1929,2017],'volume_count':len(volumes),'volumes_list':sorted(volumes),'issue_position_count':len(issues),'issues':[[v,i] for v,i in sorted(issues)],'issue_numbers_by_volume':{str(v):x for v,x in sorted(vol_issues.items())},
 'article_row_count':len(article_rows),'pdf_link_occurrence_count':len(pdf_occ),'unique_pdf_url_count':len(unique_urls),'valid_unique_pdf_count':sum(c['ok'] for c in checks),'broken_unique_pdf_count':sum(not c['ok'] for c in checks),
 'host_distribution_occurrences':dict(host_occ),'host_distribution_unique':dict(host_unique),'duplicate_pdf_urls':dups,'unmapped_pdf_occurrence_count':len(unmapped),
 'volumes_with_pdf':sorted(v for v,n in vol_pdf.items() if n),'volumes_without_pdf':sorted(v for v in volumes if not vol_pdf[v]),'article_count_by_volume':dict(sorted(vol_articles.items())),'pdf_occurrence_count_by_volume':dict(sorted(vol_pdf.items())),
 'page_stats':page_stats,'broken_links':[c for c in checks if not c['ok']],
}
open('eq_inventory_summary.json','w',encoding='utf-8').write(json.dumps(summary,ensure_ascii=False,indent=2))
open('eq_articles.json','w',encoding='utf-8').write(json.dumps(article_rows,ensure_ascii=False,indent=2))
with open('eq_pdf_manifest.csv','w',newline='',encoding='utf-8') as f:
    fields=['volume','issue','year_text','pages','title','text','page','url','anchor_text','ok','status','content_type','final_url','host','pdf_header','error']; w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for p in pdf_occ:
        row={k:p.get(k) for k in fields[:9]}; row.update({k:p['validation'].get(k) for k in fields[9:]}); w.writerow(row)
print('SUMMARY_JSON='+json.dumps(summary,ensure_ascii=False,separators=(',',':')),flush=True)
