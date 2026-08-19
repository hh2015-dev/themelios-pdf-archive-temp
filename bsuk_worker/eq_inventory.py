from __future__ import annotations
import csv, json, re, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE='https://biblicalstudies.gospelstudies.org.uk/'
PAGES=['articles_evangelical_quarterly.php']+[f'articles_evangelical_quarterly-{i:02d}.php' for i in range(1,9)]
OUT=Path('eq_inventory_out'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36 BSUK-EQ-Inventory/2.0'


def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def absurl(href, page_url): return urljoin(page_url, href)
def is_pdf_href(href):
    h=(href or '').lower().split('#')[0]
    return h.endswith('.pdf') or '/pdf/' in h and '.pdf' in h

def extract_title(text):
    m=re.search(r'(?i)\b(?:The\s+)?Evangelical(?:\s+Quarterly)?\s+\d{1,3}\.\d{1,2}\b', text)
    pre=text[:m.start()] if m else text
    q1=pre.find('"'); q2=pre.rfind('"')
    if q1>=0 and q2>q1: return clean(pre[q1+1:q2])
    # fallback for occasional malformed quotation marks: remove author up to first comma
    bits=pre.split(',',1)
    return clean(bits[1] if len(bits)>1 else pre).strip(' "')

def extract_pages(text, vol, issue):
    # Prefer the range immediately after the journal citation/date.
    pat=rf'(?i)(?:The\s+)?Evangelical(?:\s+Quarterly)?\s+{vol}\.{issue}\s*\([^)]*\)\s*[:;,]?\s*(\d+)\s*[-–]\s*(\d+)'
    m=re.search(pat,text)
    if m:return int(m.group(1)),int(m.group(2))
    # Some entries omit/garble punctuation; use the last plausible range before pdf/end.
    prefix=re.split(r'(?i)\bpdf\b',text,1)[0]
    ranges=re.findall(r'(?<!\d)(\d{1,4})\s*[-–]\s*(\d{1,4})(?!\d)',prefix)
    if ranges:
        a,b=ranges[-1]; return int(a),int(b)
    # Single-page item.
    m=re.search(rf'(?i)(?:The\s+)?Evangelical(?:\s+Quarterly)?\s+{vol}\.{issue}\s*\([^)]*\)\s*[:;,]?\s*(\d+)\s*\.',text)
    if m:return int(m.group(1)),int(m.group(1))
    return None,None

def fetch_page(url):
    s=requests.Session(); s.headers.update({'User-Agent':UA})
    last=None
    for k in range(4):
        try:
            r=s.get(url,timeout=60); r.raise_for_status(); return r.text, r.status_code
        except Exception as e:
            last=e; time.sleep(2**k)
    raise RuntimeError(f'page fetch failed {url}: {last}')

def validate_pdf(url):
    s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept':'application/pdf,*/*;q=0.8'})
    last=None
    for k in range(3):
        try:
            with s.get(url,stream=True,timeout=(20,60),allow_redirects=True) as r:
                status=r.status_code; ctype=r.headers.get('content-type',''); clen=r.headers.get('content-length')
                r.raise_for_status()
                head=b''
                for chunk in r.iter_content(8192):
                    if chunk:
                        head+=chunk
                        if len(head)>=16: break
                ok=head.startswith(b'%PDF-')
                return {'url':url,'status':status,'ok_pdf_header':ok,'content_type':ctype,'content_length':int(clen) if clen and clen.isdigit() else None,'final_url':r.url,'error':None if ok else f'bad header {head[:16]!r}'}
        except Exception as e:
            last=repr(e); time.sleep(k+1)
    return {'url':url,'status':None,'ok_pdf_header':False,'content_type':None,'content_length':None,'final_url':None,'error':last}

rows=[]; issue_headings=set(); volume_year={}; full_issue_candidates=[]; orphan_pdf_links=[]; page_stats=[]
for page in PAGES:
    page_url=BASE+page
    html,status=fetch_page(page_url); soup=BeautifulSoup(html,'html.parser')
    vols=[]
    for h in soup.find_all('h3'):
        txt=clean(h.get_text(' ',strip=True)); m=re.fullmatch(r'Volume\s+(\d+)\s*\(([^)]+)\)',txt,re.I)
        if m:
            v=int(m.group(1)); y=clean(m.group(2)); volume_year[v]=y; vols.append(v)
    tr_count=0; article_count=0
    for tr in soup.find_all('tr'):
        txt=clean(tr.get_text(' ',strip=True));
        if not txt: continue
        tr_count+=1
        hm=re.fullmatch(r'(\d{1,3})\.(\d{1,2})',txt)
        links=[absurl(a.get('href'),page_url) for a in tr.find_all('a',href=True) if is_pdf_href(a.get('href'))]
        if hm:
            key=(int(hm.group(1)),int(hm.group(2))); issue_headings.add(key)
            for u in links: full_issue_candidates.append({'volume':key[0],'issue':key[1],'url':u,'row_text':txt,'page':page})
            continue
        im=re.search(r'(?i)\b(?:The\s+)?Evangelical(?:\s+Quarterly)?\s+(\d{1,3})\.(\d{1,2})\b',txt)
        if not im:
            for u in links: orphan_pdf_links.append({'url':u,'row_text':txt,'page':page})
            continue
        v,i=int(im.group(1)),int(im.group(2)); issue_headings.add((v,i)); article_count+=1
        p1,p2=extract_pages(txt,v,i)
        rows.append({
            'volume':v,'issue':i,'year_label':volume_year.get(v),
            'title':extract_title(txt),'pages_start':p1,'pages_end':p2,
            'row_text':txt,'page_source':page_url,
            'pdf_links':links,'primary_pdf_url':links[0] if links else None,
            'extra_pdf_urls':links[1:] if len(links)>1 else [],
        })
    page_stats.append({'page':page,'http_status':status,'volumes':vols,'tr_count':tr_count,'article_rows':article_count})

# Resolve year labels after all headings known.
for r in rows:r['year_label']=volume_year.get(r['volume'])

all_pdf_occurrences=[u for r in rows for u in r['pdf_links']]
all_pdf_occurrences += [x['url'] for x in full_issue_candidates] + [x['url'] for x in orphan_pdf_links]
unique_urls=sorted(set(all_pdf_occurrences))
print(f'PARSED volumes={len(volume_year)} issues={len(issue_headings)} articles={len(rows)} pdf_occurrences={len(all_pdf_occurrences)} unique_pdf_urls={len(unique_urls)}',flush=True)

validations={}
with ThreadPoolExecutor(max_workers=4) as ex:
    futs={ex.submit(validate_pdf,u):u for u in unique_urls}
    done=0
    for fut in as_completed(futs):
        x=fut.result(); validations[x['url']]=x; done+=1
        if done%50==0 or not x['ok_pdf_header']:
            print(f'VALIDATE {done}/{len(unique_urls)} ok={x["ok_pdf_header"]} status={x["status"]} {x["url"]} {x["error"] or ""}',flush=True)

# Detect URL collisions between distinct article records.
url_rows=defaultdict(list)
for idx,r in enumerate(rows):
    for u in r['pdf_links']: url_rows[u].append(idx)
collisions=[]
for u,idxs in url_rows.items():
    sig={(rows[j]['volume'],rows[j]['issue'],rows[j]['title'],rows[j]['pages_start'],rows[j]['pages_end']) for j in idxs}
    if len(sig)>1:
        collisions.append({'url':u,'article_indexes':idxs,'articles':[{'volume':rows[j]['volume'],'issue':rows[j]['issue'],'title':rows[j]['title'],'pages':[rows[j]['pages_start'],rows[j]['pages_end']]} for j in idxs]})
collision_urls={c['url'] for c in collisions}

# Article/link status and per-issue classification.
for r in rows:
    r['primary_link_ok']=bool(r['primary_pdf_url'] and validations.get(r['primary_pdf_url'],{}).get('ok_pdf_header'))
    r['has_url_collision']=any(u in collision_urls for u in r['pdf_links'])

issue_rows=defaultdict(list)
for idx,r in enumerate(rows): issue_rows[(r['volume'],r['issue'])].append(idx)
issue_records=[]
for v,i in sorted(issue_headings):
    idxs=issue_rows.get((v,i),[]); arts=[rows[j] for j in idxs]
    n=len(arts); linked=sum(bool(a['pdf_links']) for a in arts); valid=sum(bool(a['primary_link_ok']) for a in arts)
    coll=any(a['has_url_collision'] for a in arts)
    full=[x for x in full_issue_candidates if x['volume']==v and x['issue']==i]
    full_ok=any(validations.get(x['url'],{}).get('ok_pdf_header') for x in full)
    complete=bool(n and linked==n and valid==n and not coll)
    if full_ok: cls='full_issue_pdf'
    elif complete: cls='complete_article_set'
    elif valid: cls='partial_article_pdfs'
    else: cls='no_valid_pdfs'
    issue_records.append({'volume':v,'issue':i,'year_label':volume_year.get(v),'article_rows':n,'articles_with_pdf_link':linked,'articles_with_valid_primary_pdf':valid,'url_collision':coll,'full_issue_pdf_links':[x['url'] for x in full],'full_issue_pdf_valid':full_ok,'classification':cls})

hosts=Counter(urlparse(u).netloc.lower() for u in all_pdf_occurrences)
unique_hosts=Counter(urlparse(u).netloc.lower() for u in unique_urls)
broken=[x for x in validations.values() if not x['ok_pdf_header']]
missing_pages=[{'volume':r['volume'],'issue':r['issue'],'title':r['title'],'row_text':r['row_text']} for r in rows if r['pages_start'] is None]
missing_titles=[{'volume':r['volume'],'issue':r['issue'],'row_text':r['row_text']} for r in rows if not r['title']]
issue_counts=Counter(v for v,i in issue_headings)
volumes_with_pdfs=sorted({r['volume'] for r in rows if r['primary_link_ok']})
complete_issues=[x for x in issue_records if x['classification']=='complete_article_set']
partial_issues=[x for x in issue_records if x['classification']=='partial_article_pdfs']
zero_issues=[x for x in issue_records if x['classification']=='no_valid_pdfs']
full_issue_issues=[x for x in issue_records if x['classification']=='full_issue_pdf']

# Expected archive file target under project rules: valid full issue PDF preferred; otherwise one reconstructed PDF
# for a complete article set; otherwise each valid article PDF independently. Extra revised/non-primary links are not counted.
archive_target=0
for x in issue_records:
    if x['classification'] in ('full_issue_pdf','complete_article_set'): archive_target+=1
    elif x['classification']=='partial_article_pdfs': archive_target+=x['articles_with_valid_primary_pdf']

summary={
    'year_range':[min(int(re.search(r'\d{4}',y).group()) for y in volume_year.values() if re.search(r'\d{4}',y)), max(int(z) for y in volume_year.values() for z in re.findall(r'\d{4}',y))],
    'volume_count':len(volume_year),'volumes':sorted(volume_year),'volume_year':volume_year,
    'issue_count':len(issue_headings),'issue_count_by_volume':dict(sorted(issue_counts.items())),
    'article_count':len(rows),'articles_with_any_pdf_link':sum(bool(r['pdf_links']) for r in rows),'articles_without_pdf_link':sum(not r['pdf_links'] for r in rows),
    'pdf_link_occurrences':len(all_pdf_occurrences),'unique_pdf_urls':len(unique_urls),
    'host_distribution_occurrences':dict(hosts),'host_distribution_unique_urls':dict(unique_hosts),
    'validated_pdf_urls':sum(x['ok_pdf_header'] for x in validations.values()),'broken_or_nonpdf_urls':len(broken),
    'full_issue_pdf_issue_count':len(full_issue_issues),'complete_article_set_issue_count':len(complete_issues),'partial_article_pdf_issue_count':len(partial_issues),'zero_valid_pdf_issue_count':len(zero_issues),
    'volume_folders_needed':len(volumes_with_pdfs),'volumes_with_valid_pdfs':volumes_with_pdfs,
    'url_collision_count':len(collisions),'missing_page_range_count':len(missing_pages),'missing_title_count':len(missing_titles),
    'archive_target_files_expected':archive_target,
    'page_stats':page_stats,
}

(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'issues.json').write_text(json.dumps(issue_records,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'validations.json').write_text(json.dumps(sorted(validations.values(),key=lambda x:x['url']),ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'anomalies.json').write_text(json.dumps({'collisions':collisions,'broken_or_nonpdf':broken,'missing_pages':missing_pages,'missing_titles':missing_titles,'full_issue_candidates':full_issue_candidates,'orphan_pdf_links':orphan_pdf_links},ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
    fields=['volume','issue','year_label','title','pages_start','pages_end','primary_pdf_url','primary_link_ok','has_url_collision','page_source']
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();
    for r in rows:w.writerow({k:r.get(k) for k in fields})
with (OUT/'summary.txt').open('w',encoding='utf-8') as f:
    for k,v in summary.items(): f.write(f'{k}={json.dumps(v,ensure_ascii=False)}\n')
    f.write('BROKEN='+json.dumps(broken,ensure_ascii=False)+'\n')
    f.write('COLLISIONS='+json.dumps(collisions,ensure_ascii=False)+'\n')

print('SUMMARY_JSON='+json.dumps(summary,ensure_ascii=False),flush=True)
print('BROKEN='+json.dumps(broken,ensure_ascii=False),flush=True)
print('COLLISIONS='+json.dumps(collisions,ensure_ascii=False),flush=True)
if sorted(volume_year)!=list(range(1,90)):
    raise SystemExit(f'Unexpected volume sequence: {sorted(volume_year)}')
if missing_titles or missing_pages:
    print('WARNING metadata parse gaps present; inspect anomalies artifact',flush=True)
