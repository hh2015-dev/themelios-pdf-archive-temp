import csv, json, re, sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE = 'https://biblicalstudies.gospelstudies.org.uk/'
PAGES = [
    'articles_evangelical_quarterly.php',
    *[f'articles_evangelical_quarterly-{i:02d}.php' for i in range(1,9)]
]
UA = {'User-Agent':'Mozilla/5.0 BSUK-EQ-Inventory/1.0'}
ART_RE = re.compile(r'(?:The\s+)?Evangelical Quarterly\s+(\d{1,2})[\.:](\d)\s*\(([^)]*)\)\s*:\s*([0-9]+(?:\s*[-–]\s*[0-9]+)?)', re.I)
ISSUE_RE = re.compile(r'^\s*(\d{1,2})\.(\d)\s*$')
VOL_RE = re.compile(r'Volume\s+(\d{1,2})\s*\(([^)]*)\)', re.I)

session = requests.Session(); session.headers.update(UA)
articles=[]; issues=set(); volumes={}; pdf_occurrences=[]; page_stats=[]

for page in PAGES:
    url=urljoin(BASE,page)
    r=session.get(url,timeout=30); r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    for s in soup.stripped_strings:
        m=ISSUE_RE.match(s)
        if m: issues.add((int(m.group(1)),int(m.group(2))))
        m=VOL_RE.search(s)
        if m: volumes[int(m.group(1))]=m.group(2).strip()
    before_a=len(articles); before_p=len(pdf_occurrences)
    seen_rows=set()
    for tr in soup.find_all('tr'):
        text=' '.join(tr.stripped_strings)
        m=ART_RE.search(text)
        if not m: continue
        vol,iss=int(m.group(1)),int(m.group(2)); issues.add((vol,iss))
        year=m.group(3).strip(); pages=m.group(4).replace('–','-').replace(' ','')
        title=''
        qm=re.search(r'[“"]([^”"]+)[”"]',text)
        if qm: title=qm.group(1).strip()
        links=[]
        for a in tr.find_all('a',href=True):
            href=urljoin(url,a['href'])
            if '.pdf' in href.lower() or a.get_text(' ',strip=True).lower().endswith('pdf'):
                links.append(href)
        key=(vol,iss,year,pages,title,text)
        if key not in seen_rows:
            seen_rows.add(key)
            articles.append({'volume':vol,'issue':iss,'year_text':year,'pages':pages,'title':title,'text':text,'page':page,'pdf_links':links})
        for href in links:
            pdf_occurrences.append({'volume':vol,'issue':iss,'year_text':year,'pages':pages,'title':title,'page':page,'url':href})
    # Catch PDF anchors outside recognized rows, for diagnostics.
    all_pdf=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(url,a['href'])
        if '.pdf' in href.lower(): all_pdf.append(href)
    recognized=[x['url'] for x in pdf_occurrences[before_p:]]
    page_stats.append({'page':page,'articles':len(articles)-before_a,'recognized_pdf_occurrences':len(recognized),'all_pdf_anchors':len(all_pdf),'unmatched_pdf_anchors':sorted(set(all_pdf)-set(recognized))})

# Deduplicate article rows accidentally repeated by malformed HTML, conservatively by bibliographic identity.
uniq={}
for a in articles:
    k=(a['volume'],a['issue'],a['year_text'],a['pages'],a['title'])
    uniq.setdefault(k,a)
articles=list(uniq.values())

# Rebuild PDF occurrence list from deduplicated articles.
pdf_occurrences=[]
for a in articles:
    for u in a['pdf_links']:
        pdf_occurrences.append({**{k:a[k] for k in ('volume','issue','year_text','pages','title','page')},'url':u})

unique_urls=sorted(set(x['url'] for x in pdf_occurrences))

def check(url):
    out={'url':url,'ok':False,'status':None,'content_type':'','final_url':'','host':'','pdf_header':False,'error':''}
    try:
        rr=requests.get(url,headers={**UA,'Range':'bytes=0-15'},stream=True,timeout=25,allow_redirects=True)
        out['status']=rr.status_code; out['content_type']=rr.headers.get('content-type',''); out['final_url']=rr.url; out['host']=urlparse(rr.url).netloc.lower()
        b=next(rr.iter_content(16),b''); rr.close()
        out['pdf_header']=b.startswith(b'%PDF-'); out['ok']=(200 <= out['status'] < 400 and out['pdf_header'])
    except Exception as e: out['error']=repr(e); out['host']=urlparse(url).netloc.lower()
    return out

checks=[]
with ThreadPoolExecutor(max_workers=4) as ex:
    futs={ex.submit(check,u):u for u in unique_urls}
    for i,f in enumerate(as_completed(futs),1):
        checks.append(f.result())
        if i%100==0 or i==len(futs): print(f'CHECKED {i}/{len(futs)}',flush=True)

check_by={c['url']:c for c in checks}
for p in pdf_occurrences:
    p['validation']=check_by.get(p['url'],{})

host_occ=Counter((check_by.get(p['url'],{}).get('host') or urlparse(p['url']).netloc.lower()) for p in pdf_occurrences)
host_unique=Counter((c.get('host') or urlparse(c['url']).netloc.lower()) for c in checks)

vol_issue_counts=defaultdict(list)
for v,i in sorted(issues): vol_issue_counts[v].append(i)
vol_pdf=Counter(p['volume'] for p in pdf_occurrences)
vol_articles=Counter(a['volume'] for a in articles)

summary={
 'source_pages':PAGES,
 'year_range':[1929,2017],
 'volumes_list':sorted(volumes),
 'volume_count':len(volumes),
 'issues':[[v,i] for v,i in sorted(issues)],
 'issue_position_count':len(issues),
 'issue_numbers_by_volume':{str(v):xs for v,xs in sorted(vol_issue_counts.items())},
 'article_count':len(articles),
 'pdf_link_occurrence_count':len(pdf_occurrences),
 'unique_pdf_url_count':len(unique_urls),
 'valid_unique_pdf_count':sum(c['ok'] for c in checks),
 'broken_unique_pdf_count':sum(not c['ok'] for c in checks),
 'host_distribution_occurrences':dict(host_occ),
 'host_distribution_unique':dict(host_unique),
 'volumes_with_pdf':sorted(v for v,n in vol_pdf.items() if n),
 'volumes_without_pdf':sorted(v for v in volumes if not vol_pdf[v]),
 'article_count_by_volume':dict(sorted(vol_articles.items())),
 'pdf_count_by_volume':dict(sorted(vol_pdf.items())),
 'page_stats':page_stats,
 'broken_links':[c for c in checks if not c['ok']],
 'duplicate_pdf_urls':{u:sum(1 for p in pdf_occurrences if p['url']==u) for u in unique_urls if sum(1 for p in pdf_occurrences if p['url']==u)>1},
}
open('eq_inventory_summary.json','w',encoding='utf-8').write(json.dumps(summary,ensure_ascii=False,indent=2))
open('eq_articles.json','w',encoding='utf-8').write(json.dumps(articles,ensure_ascii=False,indent=2))
with open('eq_pdf_manifest.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=['volume','issue','year_text','pages','title','page','url','ok','status','content_type','final_url','host','pdf_header','error'])
    w.writeheader()
    for p in pdf_occurrences:
        c=p['validation']; row={k:p[k] for k in ('volume','issue','year_text','pages','title','page','url')}; row.update({k:c.get(k) for k in ('ok','status','content_type','final_url','host','pdf_header','error')}); w.writerow(row)
print('SUMMARY_JSON='+json.dumps(summary,ensure_ascii=False,separators=(',',':')),flush=True)
