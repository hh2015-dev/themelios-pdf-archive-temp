import json,re,os,shutil,urllib.request,urllib.parse,unicodedata,difflib
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from pypdf import PdfReader,PdfWriter

TARGETS={(55,2),(56,3),(58,1),(59,2),(59,3),(60,2),(60,3),(61,2),(61,4),(63,3)}
OUT=Path('jets-repairs'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 JETS-archive-repair/3.0'
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
    with urllib.request.urlopen(req,timeout=35) as r:return r.read()

def safe_url(url): return urllib.parse.quote(url,safe=':/?=&%#')

def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def cit_title(c):
    m=re.search(r'[“\"]([^”\"]+)[”\"]',c)
    return m.group(1).strip() if m else c.split(', Journal of')[0].strip()

def page_range(c):
    m=re.search(r':\s*(\d+)\s*[-–]\s*(\d+)\.?\s*(?:pdf:)?\s*$',c,re.I)
    return f'pp {m.group(1)}-{m.group(2)}' if m else ''

def clean_name(s,maxlen=155):
    s=re.sub(r'[\\/:*?"<>|]+',' - ',s)
    s=' '.join(s.split()).strip(' .-')
    return s[:maxlen].rstrip(' .-')

def official_links(vol):
    last=None
    for u in [f'https://etsjets.org/jets-volume/jets{vol}/',f'https://etsjets.org/jets{vol}/']:
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
        candidates.append((max(score,ov),href,text))
    candidates.sort(reverse=True)
    if not candidates or candidates[0][0]<0.55:
        raise RuntimeError(f'no reliable official match; best={candidates[:2]}')
    return candidates[0]

def migrated_candidates(url,vol,no,year):
    dec=urllib.parse.unquote(url)
    m=re.search(r'/files/JETS-PDFs/(\d+)/(\d+-\d+)/([^?#]+\.pdf)',dec,re.I)
    if not m:return []
    fname=m.group(3); wpname=f'files_JETS-PDFs_{vol}_{vol}-{no}_{fname}'
    enc=urllib.parse.quote(wpname,safe='-_.()%')
    months=[3,4,6,7,9,10,12,1,2,5,8,11]
    return [f'https://etsjets.org/wp-content/uploads/{yy}/{mm:02d}/{enc}' for yy in [year,year+1] for mm in months]

def fetch_pdf(url,dest):
    data=get(safe_url(url))
    if not data.startswith(b'%PDF'):raise ValueError('not PDF')
    dest.write_bytes(data); return len(PdfReader(str(dest),strict=False).pages)

def dl(item,dest):
    errors=[]
    # First preserve the exact BiblicalStudies-indexed target.
    try:
        p=fetch_pdf(item['url'],dest)
        return {'ok':True,'url':safe_url(item['url']),'pages':p,'repair_kind':'indexed'}
    except Exception as e: errors.append(f'indexed:{type(e).__name__}:{e}')
    try:
        score,href,text=official_match(item['volume'],item['citation'])
    except Exception as e:
        return {'ok':False,'error':' | '.join(errors+[f'official-match:{e!r}'])}
    attempts=[(href,'official-current')]
    for base in [item['url'],href]:
        for u in migrated_candidates(base,item['volume'],item['issue'],item['year']):
            if u not in [x for x,_ in attempts]:attempts.append((u,'official-migrated'))
    for url,kind in attempts:
        try:
            p=fetch_pdf(url,dest)
            return {'ok':True,'url':safe_url(url),'pages':p,'repair_kind':kind,'match_score':score,'official_anchor':text}
        except Exception as e: errors.append(f'{kind}:{safe_url(url)} => {type(e).__name__}:{e}')
    return {'ok':False,'error':' | '.join(errors[-10:]),'official_anchor':text,'match_score':score}

reports=[]
for issue in manifest['issues']:
    key=(issue['volume'],issue['issue'])
    if key not in TARGETS:continue
    vol,no=key; year=issue['year']; work=OUT/f'_w_{vol}_{no}'; work.mkdir(exist_ok=True)
    results=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs=[]
        for idx,x in enumerate(issue['pdfs'],1):
            y=dict(x);y.update({'volume':vol,'issue':no,'year':year})
            path=work/f'{idx:03d}.pdf'; futs.append((idx,y,path,ex.submit(dl,y,path)))
        for idx,x,path,f in futs:
            try:r=f.result()
            except Exception as e:r={'ok':False,'error':repr(e)}
            r.update({'index':idx,'citation':x['citation'],'title':cit_title(x['citation']),'path':str(path)})
            results.append(r)
    ok=[r for r in results if r['ok']]; bad=[r for r in results if not r['ok']]
    title='Bulletin of the Evangelical Theological Society' if issue['series']=='BETS' else 'Journal of the Evangelical Theological Society'
    outputs=[]
    if not bad:
        fname=f'{title} - Volume {vol:03d} Issue {no:02d} - {year} - Reconstructed from official article PDFs.pdf'
        writer=PdfWriter(); pages=0
        for r in sorted(ok,key=lambda z:z['index']):
            rd=PdfReader(r['path'],strict=False)
            for p in rd.pages:writer.add_page(p);pages+=1
        out=OUT/fname
        with out.open('wb') as f:writer.write(f)
        if len(PdfReader(str(out),strict=False).pages)!=pages:raise RuntimeError('page validation failed')
        outputs.append(fname)
        status='FULL_RECONSTRUCTED'
        print(f'REPAIRED {vol}.{no}: FULL {len(ok)}/{len(results)} sources -> {pages} pages')
    else:
        status='PARTIAL_INDIVIDUAL_ARTICLES'
        for r in sorted(ok,key=lambda z:z['index']):
            pg=page_range(r['citation']); art=clean_name(r['title'])
            fname=f'{title} - Volume {vol:03d} Issue {no:02d} - {year} - {art}' + (f' - {pg}' if pg else '') + '.pdf'
            shutil.copy2(r['path'],OUT/fname)
            PdfReader(str(OUT/fname),strict=False)
            outputs.append(fname)
        print(f'REPAIRED {vol}.{no}: PARTIAL {len(ok)}/{len(results)} available; {len(bad)} official/indexed links unavailable')
    reports.append({'volume':vol,'issue':no,'year':year,'status':status,'expected_articles':len(results),'available_articles':len(ok),'outputs':outputs,'failed_items':[{'index':r['index'],'citation':r['citation'],'title':r['title'],'error':r.get('error')} for r in bad]})
    for p in work.glob('*'):p.unlink()
    work.rmdir()
json.dump({'targets':len(TARGETS),'handled':len(reports),'reports':reports},open(OUT/'repair_report.json','w'),ensure_ascii=False,indent=2)
print('DONE targets=',len(TARGETS),'handled=',len(reports),'full=',sum(r['status']=='FULL_RECONSTRUCTED' for r in reports),'partial=',sum(r['status']=='PARTIAL_INDIVIDUAL_ARTICLES' for r in reports))
