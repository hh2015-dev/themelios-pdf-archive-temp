from bs4 import BeautifulSoup
from urllib.parse import urljoin
from collections import Counter, defaultdict
from pathlib import Path
from pypdf import PdfReader, PdfWriter
import fitz
import hashlib, json, os, re, requests, shutil, sys, time

BASE='https://www.biblicalstudies.org.uk/'
VOLUME=int(sys.argv[1])
YEAR=1929+VOLUME
OUT=Path('bible_student_output')/f'Volume {VOLUME:03d}'
DIAG=OUT/'_diagnostics'
OUT.mkdir(parents=True,exist_ok=True); DIAG.mkdir(exist_ok=True)
TMP=Path('bible_student_tmp')/str(VOLUME); TMP.mkdir(parents=True,exist_ok=True)
HEADERS={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'}
S=requests.Session(); S.headers.update(HEADERS)
PAGES=[urljoin(BASE,f'articles_bible-student_{n:02d}.php') for n in range(1,5)]

_illegal=re.compile(r'[<>:"/\\|?*\x00-\x1f]')
def safe(s,n=125):
    s=_illegal.sub('-',s); s=re.sub(r'\s+',' ',s).strip(' .-')
    return s[:n].rstrip(' .-') or 'Untitled'

def title_from_context(ctx):
    m=re.search(r'["“](.*?)["”]',ctx)
    if m: return m.group(1).strip(' ,')
    # fallback before journal title
    x=ctx.split('The Bible Student')[0].strip(' ,')
    return x[-100:] if x else 'Untitled'

def pages_from_context(ctx):
    m=re.search(r'\):\s*([0-9][0-9,\-–— ]*)\.?\s*pdf\b',ctx,re.I)
    return re.sub(r'\s+',' ',m.group(1)).strip() if m else ''

def first_page(ctx):
    p=pages_from_context(ctx)
    m=re.search(r'\d+',p)
    return int(m.group()) if m else None

def href_issue(url):
    m=re.search(r'bible-student_(\d+)-(\d+)_',url,re.I)
    return (int(m.group(1)),int(m.group(2))) if m else None

def expected_url(rec):
    p=first_page(rec['context'])
    if p is None:return None
    return urljoin(BASE,f'pdf/bible-student/bible-student_{rec["volume"]}-{rec["issue"]}_{p:03d}.pdf')

def parse_all_records():
    records=[]; page_meta=[]
    for page in PAGES:
        r=S.get(page,timeout=60); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        page_meta.append({'url':page,'status':r.status_code,'bytes':len(r.content),'title':soup.title.get_text(' ',strip=True) if soup.title else ''})
        for h3 in soup.find_all('h3'):
            m=re.search(r'Volume\s+(\d+)\s*\((\d{4})\)',h3.get_text(' ',strip=True))
            if not m:continue
            vol=int(m.group(1)); year=int(m.group(2)); table=h3.find_next('table')
            if not table:continue
            cur_issue=None; order=0
            for tr in table.find_all('tr',recursive=False):
                text=' '.join(tr.stripped_strings)
                im=re.fullmatch(r'(\d+)\.(\d+)',text.strip())
                if im:
                    cur_issue=int(im.group(2)); order=0; continue
                if cur_issue is None:continue
                a=next((aa for aa in tr.find_all('a',href=True) if '/pdf/bible-student/' in urljoin(page,aa['href']).lower()),None)
                if not a:continue
                order+=1
                ctx=re.sub(r'\s+',' ',' '.join(a.stripped_strings)).strip()
                records.append({'volume':vol,'year':year,'issue':cur_issue,'order':order,'url':urljoin(page,a['href']),'context':ctx,'title':title_from_context(ctx),'pages':pages_from_context(ctx)})
    # exact record dedupe only; preserves distinct article records sharing one URL
    out=[]; seen=set()
    for r in records:
        sig=(r['volume'],r['issue'],r['url'],r['context'])
        if sig in seen:continue
        seen.add(sig);out.append(r)
    return out,page_meta

ALL,PAGE_META=parse_all_records()
url_records=defaultdict(list)
for r in ALL:url_records[r['url']].append(r)

cache={}
def download(url,label):
    if url in cache:return cache[url]
    path=TMP/(hashlib.sha1(url.encode()).hexdigest()+'.pdf')
    err=None
    for attempt in range(3):
        try:
            rr=S.get(url,timeout=90,allow_redirects=True)
            if rr.status_code!=200: raise RuntimeError(f'HTTP {rr.status_code}')
            data=rr.content
            if not data.startswith(b'%PDF-'): raise RuntimeError('not PDF magic')
            path.write_bytes(data)
            doc=fitz.open(path)
            if doc.page_count<1: raise RuntimeError('zero pages')
            text='\n'.join(doc[i].get_text('text') for i in range(min(2,doc.page_count)))[:8000]
            # preview first page for anomalous/recovered records
            info={'ok':True,'path':str(path),'bytes':len(data),'pages':doc.page_count,'text_sample':text,'final_url':rr.url}
            doc.close(); cache[url]=info; return info
        except Exception as e:
            err=repr(e); time.sleep(1+attempt)
    info={'ok':False,'path':None,'error':err}; cache[url]=info; return info

def render_preview(pdf_path,name):
    try:
        doc=fitz.open(pdf_path); page=doc[0]; pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
        pix.save(str(DIAG/safe(name,80))+'.png'); doc.close()
    except Exception:pass

def norm_words(s):
    return {w for w in re.findall(r'[a-z0-9]+',s.lower()) if len(w)>=4}

def title_score(title,text):
    a=norm_words(title); b=norm_words(text)
    return (len(a&b)/len(a)) if a else 0.0

records=[dict(r) for r in ALL if r['volume']==VOLUME]
issues=defaultdict(list)
for r in records: issues[r['issue']].append(r)
manifest={'volume':VOLUME,'year':YEAR,'source_pages':PAGE_META,'issues':{},'outputs':[],'warnings':[]}

# Resolve every record conservatively.
for r in records:
    actual=r['url']; exp=expected_url(r); group=url_records[actual]; conflict=len({x['context'] for x in group})>1
    mismatch=href_issue(actual)!=(r['volume'],r['issue'])
    r.update({'expected_url':exp,'source_url_conflict':conflict,'source_issue_mismatch':mismatch,'selected_url':None,'resolution':None,'available':False})
    # ordinary official link
    if not conflict and not mismatch:
        info=download(actual,'ordinary')
        if info['ok']:
            r.update({'selected_url':actual,'resolution':'linked_source_pdf','available':True,'pdf_pages':info['pages'],'bytes':info['bytes']})
        else:r['resolution']='linked_pdf_failed';r['error']=info.get('error')
        continue
    # If the source link is reused, keep it for the one record whose expected path is exactly that link,
    # unless multiple records make that same claim (then it is ambiguous).
    same_claim=[x for x in group if expected_url(x)==actual]
    if conflict and exp==actual and len(same_claim)==1:
        info=download(actual,'conflict-owner')
        if info['ok']:
            r.update({'selected_url':actual,'resolution':'linked_source_pdf_unique_owner_of_reused_url','available':True,'pdf_pages':info['pages'],'bytes':info['bytes']})
        else:r['resolution']='linked_pdf_failed';r['error']=info.get('error')
        continue
    # Try the exact official BiblicalStudies path implied by this record's issue + cited starting page.
    if exp and exp!=actual:
        info=download(exp,'recovery')
        if info['ok']:
            score=title_score(r['title'],info.get('text_sample',''))
            r.update({'selected_url':exp,'resolution':'recovered_on_primary_BiblicalStudies_host','available':True,'pdf_pages':info['pages'],'bytes':info['bytes'],'title_text_score':round(score,3)})
            render_preview(info['path'],f'{VOLUME}-{r["issue"]}-{r["order"]}-recovered')
            continue
    # Ambiguous reused URL: inspect linked PDF text; assign only when one article title clearly matches.
    if conflict:
        info=download(actual,'ambiguous')
        if info['ok']:
            scores=[(title_score(x['title'],info.get('text_sample','')),x) for x in group]
            scores.sort(key=lambda z:z[0],reverse=True)
            mine=title_score(r['title'],info.get('text_sample',''))
            if mine>=0.65 and (len(scores)==1 or scores[0][0]-scores[1][0]>=0.20) and scores[0][1]['context']==r['context']:
                r.update({'selected_url':actual,'resolution':'ambiguous_link_resolved_by_pdf_text','available':True,'pdf_pages':info['pages'],'bytes':info['bytes'],'title_text_score':round(mine,3)})
                continue
            render_preview(info['path'],f'{VOLUME}-{r["issue"]}-{r["order"]}-ambiguous')
    r['resolution']='unresolved_source_link_anomaly'

# Build outputs issue-by-issue.
def page_fingerprint(page):
    pix=page.get_pixmap(matrix=fitz.Matrix(1.0,1.0),colorspace=fitz.csGRAY,alpha=False)
    return hashlib.sha256(pix.samples).hexdigest()

def merge_records(recs,outpath):
    outdoc=fitz.open(); last_fp=None; added=0; skipped_overlap=0
    for rec in recs:
        info=download(rec['selected_url'],'merge'); doc=fitz.open(info['path'])
        start=0
        if doc.page_count and last_fp is not None:
            fp=page_fingerprint(doc[0])
            if fp==last_fp:
                start=1; skipped_overlap+=1
        for i in range(start,doc.page_count): outdoc.insert_pdf(doc,from_page=i,to_page=i); added+=1
        if doc.page_count:
            last_fp=page_fingerprint(doc[-1])
        doc.close()
    outdoc.save(outpath,garbage=3,deflate=True); outdoc.close()
    chk=fitz.open(outpath); pc=chk.page_count; chk.close()
    return {'pages':pc,'skipped_adjacent_duplicate_pages':skipped_overlap,'inserted_pages':added}

for issue,recs in sorted(issues.items()):
    recs=sorted(recs,key=lambda x:x['order'])
    selected=[r for r in recs if r['available']]
    selected_urls=[r['selected_url'] for r in selected]
    complete=len(selected)==len(recs) and len(set(selected_urls))==len(selected_urls)
    im={'issue':issue,'listed_articles':len(recs),'resolved_articles':len(selected),'complete':complete,'records':recs,'outputs':[]}
    if complete:
        name=f'The Bible Student - Volume {VOLUME:03d} Issue {issue:02d} - {YEAR} - Reconstructed from official article PDFs.pdf'
        path=OUT/name
        mi=merge_records(recs,path)
        # strict local validation
        rr=PdfReader(str(path)); assert len(rr.pages)>0
        im['merge']=mi; im['outputs'].append(name); manifest['outputs'].append(name)
    else:
        manifest['warnings'].append(f'Volume {VOLUME:03d} Issue {issue:02d} incomplete: {len(selected)}/{len(recs)} official article records resolved')
        used=set()
        for r in selected:
            if r['selected_url'] in used:continue
            used.add(r['selected_url'])
            info=download(r['selected_url'],'individual')
            pages=safe(r['pages'],35)
            title=safe(r['title'],105)
            suffix=f' - pp {pages}' if pages else ''
            name=f'The Bible Student - Volume {VOLUME:03d} Issue {issue:02d} - {YEAR} - {title}{suffix}.pdf'
            dest=OUT/name
            shutil.copy2(info['path'],dest)
            rr=PdfReader(str(dest)); assert len(rr.pages)>0
            im['outputs'].append(name); manifest['outputs'].append(name)
    manifest['issues'][str(issue)]=im

# Remove diagnostic dir if empty; keep it in artifact only when anomalies need human inspection.
if DIAG.exists() and not any(DIAG.iterdir()): DIAG.rmdir()
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'volume':VOLUME,'year':YEAR,'issues':{k:{'listed':v['listed_articles'],'resolved':v['resolved_articles'],'complete':v['complete'],'outputs':len(v['outputs'])} for k,v in manifest['issues'].items()},'output_count':len(manifest['outputs']),'warnings':manifest['warnings']},ensure_ascii=False,indent=2))
