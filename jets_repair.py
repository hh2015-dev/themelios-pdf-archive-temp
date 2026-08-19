import json,re,os,time,urllib.request,urllib.parse,unicodedata,difflib
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from pypdf import PdfReader,PdfWriter

TARGETS={(55,2),(56,3),(58,1),(59,2),(59,3),(60,2),(60,3),(61,2),(61,4),(63,3)}
OUT=Path('jets-repairs'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 JETS-archive-repair/2.0'
manifest=json.load(open('jets_manifest.json',encoding='utf-8'))

class P(HTMLParser):
    def __init__(self,base): super().__init__(convert_charrefs=True); self.base=base; self.a=None; self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='a': self.a={'href':dict(attrs).get('href',''),'text':[]}
    def handle_data(self,data):
        if self.a is not None:self.a['text'].append(data)
    def handle_endtag(self,tag):
        if tag.lower()=='a' and self.a is not None:
            self.links.append((urllib.parse.urljoin(self.base,self.a['href']),' '.join(''.join(self.a['text']).split()))); self.a=None

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=60) as r:return r.read()

def safe_url(url):
    # Keep URL syntax and existing percent escapes, but encode spaces/non-ASCII safely.
    return urllib.parse.quote(url,safe=':/?=&%#')

def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def cit_title(c):
    m=re.search(r'[“\"]([^”\"]+)[”\"]',c)
    return m.group(1).strip() if m else c.split(', Journal of')[0]

def official_links(vol):
    urls=[f'https://etsjets.org/jets-volume/jets{vol}/',f'https://etsjets.org/jets{vol}/']
    last=None
    for u in urls:
        try:
            html=get(u).decode('utf-8','replace'); p=P(u); p.feed(html)
            pdf=[x for x in p.links if '.pdf' in x[0].lower()]
            if pdf:return pdf
        except Exception as e:last=e
    raise RuntimeError(f'cannot load official vol {vol}: {last!r}')

def official_match(vol,citation):
    title=cit_title(citation); nt=norm(title); candidates=[]
    for href,text in official_links(vol):
        score=difflib.SequenceMatcher(None,nt,norm(text)).ratio()
        toks=set(nt.split()); tt=set(norm(text).split()); ov=len(toks&tt)/max(1,len(toks))
        score=max(score,ov)
        candidates.append((score,href,text))
    candidates.sort(reverse=True)
    if not candidates or candidates[0][0]<0.55:
        raise RuntimeError(f'no reliable official match for {vol}: {title!r}; best={candidates[:3]}')
    return candidates[0]

def migrated_candidates(url,vol,no,year):
    """Generate official WordPress relocation forms for legacy /files/JETS-PDFs/... links."""
    dec=urllib.parse.unquote(url)
    m=re.search(r'/files/JETS-PDFs/(\d+)/(\d+-\d+)/([^?#]+\.pdf)',dec,re.I)
    if not m:return []
    fname=m.group(3)
    wpname=f'files_JETS-PDFs_{vol}_{vol}-{no}_{fname}'
    encname=urllib.parse.quote(wpname,safe='-_.()%')
    # Issues were commonly uploaded near Mar/Jun-Sep/Dec; also try every month, and next Jan for Dec issues.
    months=[3,4,6,7,9,10,12,1,2,5,8,11]
    years=[year,year+1]
    return [f'https://etsjets.org/wp-content/uploads/{yy}/{mm:02d}/{encname}' for yy in years for mm in months]

def fetch_pdf(url,dest):
    data=get(safe_url(url))
    if not data.startswith(b'%PDF'):raise ValueError('not PDF')
    dest.write_bytes(data)
    r=PdfReader(str(dest),strict=False)
    return len(r.pages)

def dl(item,dest):
    attempts=[]
    # 1) BiblicalStudies-indexed URL exactly as archived.
    attempts.append((item['url'],'indexed'))
    # 2) Current official volume-page match.
    score,href,text=official_match(item['volume'],item['citation'])
    if href not in [u for u,_ in attempts]: attempts.append((href,'official-current'))
    # 3) Official WordPress relocation candidates derived from both legacy paths.
    for base in [item['url'],href]:
        for u in migrated_candidates(base,item['volume'],item['issue'],item['year']):
            if u not in [x for x,_ in attempts]:attempts.append((u,'official-migrated'))
    errors=[]
    for url,kind in attempts:
        try:
            pages=fetch_pdf(url,dest)
            return {'url':safe_url(url),'pages':pages,'repaired':kind!='indexed','repair_kind':kind,'match_score':score,'official_anchor':text}
        except Exception as e:
            errors.append(f'{kind}:{safe_url(url)} => {type(e).__name__}:{e}')
    raise RuntimeError('all official candidates failed; '+ ' | '.join(errors[-8:]))

reports=[]
for issue in manifest['issues']:
    key=(issue['volume'],issue['issue'])
    if key not in TARGETS:continue
    vol,no=key; year=issue.get('year'); work=OUT/f'_w_{vol}_{no}'; work.mkdir(exist_ok=True)
    items=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs=[]
        for idx,x in enumerate(issue['pdfs'],1):
            y=dict(x);y.update({'volume':vol,'issue':no,'year':year})
            futs.append((idx,y,work/f'{idx:03d}.pdf',ex.submit(dl,y,work/f'{idx:03d}.pdf')))
        for idx,x,path,f in futs:
            try:
                r=f.result();r.update({'index':idx,'citation':x['citation']});items.append(r)
            except Exception as e:
                raise RuntimeError(f'{vol}.{no} item {idx} {x["citation"]}: {e!r}')
    title='Bulletin of the Evangelical Theological Society' if issue['series']=='BETS' else 'Journal of the Evangelical Theological Society'
    fname=f'{title} - Volume {vol:03d} Issue {no:02d} - {year} - Reconstructed from official article PDFs.pdf'
    writer=PdfWriter(); pages=0
    for idx in range(1,len(issue['pdfs'])+1):
        rd=PdfReader(str(work/f'{idx:03d}.pdf'),strict=False)
        for p in rd.pages:writer.add_page(p);pages+=1
    out=OUT/fname
    with out.open('wb') as f:writer.write(f)
    chk=PdfReader(str(out),strict=False)
    if len(chk.pages)!=pages:raise RuntimeError('page validation failed')
    reports.append({'volume':vol,'issue':no,'year':year,'file':fname,'source_pdf_count':len(items),'pages':pages,'bytes':out.stat().st_size,'repaired_items':[x for x in items if x.get('repaired')]})
    print(f'REPAIRED {vol}.{no}: {len(items)} sources -> {pages} pages; corrected={sum(x.get("repaired",False) for x in items)}')
    for p in work.iterdir():p.unlink()
    work.rmdir()
json.dump({'targets':len(TARGETS),'built':len(reports),'reports':reports},open(OUT/'repair_report.json','w'),ensure_ascii=False,indent=2)
