import csv, hashlib, json, os, re, tempfile, time
from pathlib import Path
from urllib.parse import quote
import fitz
import requests

SEARCH='https://archive.org/advancedsearch.php'
META='https://archive.org/metadata/{id}'
DL='https://archive.org/download/{id}/{name}'
OUT=Path('ashland_inventory_v2'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers['User-Agent']='BSUK-Ashland-Inventory/2.0'

TITLE_RANGE_MAP={
    (1968,1973):(1,6), (1974,1979):(7,12), (1980,1980):(13,13),
    (1987,1992):(19,24), (1993,1998):(25,30),
    (1999,2004):(31,36), (2005,2010):(37,42),
}
KNOWN_IDS={'ashlandtheologic3136bake'}

def gj(url, **kw):
    err=None
    for k in range(5):
        try:
            r=S.get(url,timeout=90,**kw); r.raise_for_status(); return r.json()
        except Exception as e: err=e; time.sleep(2**k)
    raise RuntimeError(f'JSON GET failed {url}: {err}')

def down(url,p):
    err=None
    for k in range(4):
        try:
            with S.get(url,stream=True,timeout=(30,180)) as r:
                r.raise_for_status()
                with open(p,'wb') as f:
                    for b in r.iter_content(1024*1024):
                        if b: f.write(b)
            return
        except Exception as e:
            err=e
            try: os.remove(p)
            except OSError: pass
            time.sleep(3*(k+1))
    raise RuntimeError(f'download failed {url}: {err}')

def title_year_range(title):
    ys=[int(x) for x in re.findall(r'\b(?:19|20)\d{2}\b',str(title))]
    if len(ys)>=2: return min(ys),max(ys)
    if len(ys)==1: return ys[0],ys[0]
    return None

def volume_range(value,title=''):
    if isinstance(value,list): value=' '.join(map(str,value))
    s=str(value or '')
    # Only numbers explicitly following Vol./Volume; ignore No. 1 issue numbers.
    nums=[int(x) for x in re.findall(r'(?i)\bVol(?:ume)?\.?\s*(\d{1,2})\b',s)]
    nums=[x for x in nums if 1<=x<=42]
    if len(nums)>=2: return nums[0],nums[-1]
    if len(nums)==1:
        yr=title_year_range(title)
        if yr in TITLE_RANGE_MAP and TITLE_RANGE_MAP[yr][0]==nums[0]: return TITLE_RANGE_MAP[yr]
        return nums[0],nums[0]
    yr=title_year_range(title)
    return TITLE_RANGE_MAP.get(yr)

def choose_pdf(files,ident):
    c=[]
    for f in files:
        n=f.get('name',''); fmt=str(f.get('format','')); size=int(f.get('size') or 0)
        if not n.lower().endswith('.pdf') or f.get('private') is True: continue
        sc=0
        if n==f'{ident}.pdf': sc+=1000
        if 'Text PDF' in fmt: sc+=500
        if f.get('source')=='derivative': sc+=30
        if '_bw.pdf' in n.lower(): sc-=200
        c.append((sc,size,n,fmt))
    if not c:return None
    c.sort(reverse=True); return c[0]

def discover():
    params={'q':'collection:brethrendigitalarchives AND title:Ashland','fl[]':['identifier','title','volume','date'],'rows':200,'page':1,'output':'json'}
    docs=gj(SEARCH,params=params).get('response',{}).get('docs',[])
    ids={d.get('identifier') for d in docs if d.get('identifier')}
    ids |= KNOWN_IDS
    print('SEARCH_DOCS='+json.dumps([{'identifier':d.get('identifier'),'title':d.get('title'),'volume':d.get('volume')} for d in docs],ensure_ascii=False),flush=True)
    found=[]
    for ident in sorted(ids):
        m=gj(META.format(id=ident)); md=m.get('metadata',{}); title=str(md.get('title',''))
        if 'Ashland Theological' not in title: continue
        vr=volume_range(md.get('volume'),title)
        if not vr:
            print(f'SKIP_NO_RANGE|{ident}|{title}|{md.get("volume")}',flush=True); continue
        p=choose_pdf(m.get('files',[]),ident)
        if not p:
            print(f'SKIP_NO_PDF|{ident}|{title}',flush=True); continue
        sc,sz,name,fmt=p
        found.append({'identifier':ident,'title':title,'volume_raw':md.get('volume'),'vstart':vr[0],'vend':vr[1],'pdf_name':name,'source_size':sz,'format':fmt})
    # Prefer the widest canonical record for each exact range; remove accidental duplicates.
    by={}
    for x in found:
        key=(x['vstart'],x['vend'])
        if key not in by or x['source_size']>by[key]['source_size']: by[key]=x
    out=sorted(by.values(),key=lambda x:x['vstart'])
    print('DISCOVERED_BUNDLES='+json.dumps(out,ensure_ascii=False),flush=True)
    return out

def roman(n):
    vals=[(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]; s=''
    for v,t in vals:
        while n>=v:s+=t;n-=v
    return s

def ed(a,b):
    p=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        q=[i]
        for j,cb in enumerate(b,1): q.append(min(q[-1]+1,p[j]+1,p[j-1]+(ca!=cb)))
        p=q
    return p[-1]

def norm(t): return re.sub(r'\s+',' ',t.upper().replace('–','-').replace('—','-'))
def has_title(t): return 'ASHLAND' in t and 'THEOLOGICAL' in t and ('JOURNAL' in t or 'BULLETIN' in t)
def yearof(t):
    ys=[int(y) for y in re.findall(r'\b(19\d{2}|20[01]\d)\b',t) if 1968<=int(y)<=2010]
    return max(sorted(set(ys)),key=ys.count) if ys else None

def score(t,n):
    if not has_title(t): return 0
    target=roman(n); best=0
    # Numeric journal header, e.g. Ashland Theological Journal 31 (1999)
    if re.search(rf'ASHLAND\s+THEOLOGICAL\s+(?:JOURNAL|BULLETIN)\s+0*{n}\b',t): best=80
    for tok in re.findall(r'\bVOLUME\s+([IVXL1]{1,8})\b',t):
        tok=tok.replace('1','I')
        d=ed(tok,target)
        if d==0:
            s=120 if 'CONTENTS' in t else (115 if ('PUBLISHED' in t or 'PRINTED' in t) else 100)
            best=max(best,s)
        elif d==1 and len(target)>=3:
            s=112 if 'CONTENTS' in t else 92
            best=max(best,s)
    return best

def locate(texts,a,b):
    marker={}
    for n in range(a,b+1):
        hits=[(score(t,n),i) for i,t in enumerate(texts) if score(t,n)>0]
        if not hits: marker[n]=None; continue
        mx=max(x for x,_ in hits); marker[n]=min(i for x,i in hits if x==mx)
    miss=[n for n in range(a,b+1) if marker[n] is None]
    if miss: raise RuntimeError(f'missing markers {miss}; markers={marker}')
    pp=[marker[n] for n in range(a,b+1)]
    if pp!=sorted(pp) or len(set(pp))!=len(pp): raise RuntimeError(f'non-monotonic markers {marker}')
    starts={}; years={}
    prev=-1
    for n in range(a,b+1):
        m=marker[n]; y=yearof(texts[m]); cand=[]
        for j in range(max(0,m-12),m+1):
            if has_title(texts[j]) and (y is None or yearof(texts[j])==y): cand.append(j)
        st=min(cand) if cand else m
        if st<=prev: st=m
        starts[n]=st; years[n]=y or yearof(texts[st]); prev=st
    return starts,years,marker

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def save_manifest(rows,errors):
    rows=sorted(rows,key=lambda r:r['volume'])
    (OUT/'errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    if rows:
        with open(OUT/'inventory.csv','w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with open(OUT/'inventory.md','w',encoding='utf-8') as f:
        f.write('| Volume | Year | MiB | Bytes | Pages | Bundle |\n|---:|---:|---:|---:|---:|---|\n')
        for r in rows:f.write(f"| {r['volume']} | {r['year'] or ''} | {r['size_mib']:.2f} | {r['size_bytes']} | {r['pages']} | {r['bundle_identifier']} |\n")

def main():
    items=discover(); cov=[]
    for x in items: cov+=list(range(x['vstart'],x['vend']+1))
    print('COVERAGE='+json.dumps(sorted(set(cov))),flush=True)
    rows=[]; errors=[]
    with tempfile.TemporaryDirectory(prefix='ashland_v2_') as td:
        td=Path(td)
        for it in items:
            ident=it['identifier']; src=td/(ident+'.pdf')
            try:
                url=DL.format(id=quote(ident),name=quote(it['pdf_name']))
                print(f"BUNDLE_START|{it['vstart']}-{it['vend']}|{ident}|metadata_source_bytes={it['source_size']}",flush=True)
                down(url,src); actual=src.stat().st_size
                print(f'BUNDLE_DOWNLOADED|{ident}|bytes={actual}',flush=True)
                doc=fitz.open(src); texts=[norm(doc.load_page(i).get_text('text')) for i in range(doc.page_count)]
                starts,years,markers=locate(texts,it['vstart'],it['vend']); vols=list(range(it['vstart'],it['vend']+1))
                print('BOUNDARIES|'+ident+'|'+json.dumps({'starts':starts,'years':years,'markers':markers}),flush=True)
                for k,n in enumerate(vols):
                    st=starts[n]; en=starts[vols[k+1]]-1 if k+1<len(vols) else doc.page_count-1
                    out=td/f'volume_{n:02d}.pdf'; part=fitz.open();part.insert_pdf(doc,from_page=st,to_page=en);part.save(out,garbage=4,deflate=True,clean=True);part.close()
                    sz=out.stat().st_size
                    r={'volume':n,'year':years[n],'size_bytes':sz,'size_mib':round(sz/1048576,2),'pages':en-st+1,'bundle_identifier':ident,'source_pdf':it['pdf_name'],'source_pdf_bytes':actual,'start_page_1based':st+1,'end_page_1based':en+1,'marker_page_1based':markers[n]+1,'sha256':sha(out)}
                    rows.append(r)
                    print(f"RESULT|{n}|{r['year'] or ''}|{sz}|{r['size_mib']:.2f}|{r['pages']}|{ident}|{st+1}-{en+1}|{r['sha256']}",flush=True)
                    out.unlink(); save_manifest(rows,errors)
                doc.close(); src.unlink(); print('BUNDLE_DONE|'+ident,flush=True)
            except Exception as e:
                errors.append({'identifier':ident,'range':[it['vstart'],it['vend']],'error':repr(e)})
                print(f"BUNDLE_ERROR|{ident}|{repr(e)}",flush=True)
                try: src.unlink()
                except OSError: pass
                save_manifest(rows,errors)
    save_manifest(rows,errors)
    vols=sorted(r['volume'] for r in rows)
    print('FINAL_VOLUMES='+json.dumps(vols),flush=True); print('FINAL_COUNT='+str(len(rows)),flush=True); print('ERRORS='+json.dumps(errors),flush=True)
    if vols!=list(range(1,43)) or errors: raise SystemExit(2)

if __name__=='__main__': main()
