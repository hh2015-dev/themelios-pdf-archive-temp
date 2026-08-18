import json,re,os,time,hashlib,urllib.request,urllib.parse,unicodedata,difflib
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
from pypdf import PdfReader,PdfWriter

TARGETS={(32,2),(55,2),(56,3),(58,1),(59,2),(59,3),(60,2),(60,3),(61,2),(61,4),(63,3)}
OUT=Path('jets-repairs'); OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 JETS-archive-repair/1.0'
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
        # boost overlap because anchor often has author appended
        toks=set(nt.split()); tt=set(norm(text).split()); ov=len(toks&tt)/max(1,len(toks))
        score=max(score,ov)
        candidates.append((score,href,text))
    candidates.sort(reverse=True)
    if not candidates or candidates[0][0]<0.58: raise RuntimeError(f'no reliable official match for {vol}: {title!r}; best={candidates[:2]}')
    return candidates[0]

def dl(item,dest):
    urls=[item['url']]
    last=''
    for url in urls:
        try:
            safe=urllib.parse.quote(url,safe=':/?=&%')
            data=get(safe)
            if not data.startswith(b'%PDF'):raise ValueError('not PDF')
            dest.write_bytes(data); r=PdfReader(str(dest),strict=False); return {'url':safe,'pages':len(r.pages),'repaired':False}
        except Exception as e:last=repr(e)
    score,href,text=official_match(item['volume'],item['citation'])
    safe=urllib.parse.quote(href,safe=':/?=&%')
    data=get(safe)
    if not data.startswith(b'%PDF'):raise ValueError(f'official match not PDF: {safe}')
    dest.write_bytes(data); r=PdfReader(str(dest),strict=False)
    return {'url':safe,'pages':len(r.pages),'repaired':True,'match_score':score,'official_anchor':text}

reports=[]
for issue in manifest['issues']:
    key=(issue['volume'],issue['issue'])
    if key not in TARGETS:continue
    vol,no=key; year=issue.get('year'); work=OUT/f'_w_{vol}_{no}'; work.mkdir(exist_ok=True)
    items=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs=[]
        for idx,x in enumerate(issue['pdfs'],1):
            y=dict(x);y['volume']=vol
            futs.append((idx,y,work/f'{idx:03d}.pdf',ex.submit(dl,y,work/f'{idx:03d}.pdf')))
        for idx,x,path,f in futs:
            try:r=f.result();r.update({'index':idx,'citation':x['citation']});items.append(r)
            except Exception as e:raise RuntimeError(f'{vol}.{no} item {idx} {x["citation"]}: {e!r}')
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
