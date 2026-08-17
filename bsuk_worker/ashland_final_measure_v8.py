import json, re, shutil, tempfile, time, hashlib
from pathlib import Path
import requests, fitz

S=requests.Session(); S.headers['User-Agent']='BSUK-Ashland-DriveUpload/9.0'
OUT=Path('out_ashland_upload'); OUT.mkdir(exist_ok=True)
BUNDLES=[
 ('ashlandtheologic71121alde',[7,8,9,10,12]),
 ('ashlandtheologic131kick',[13]),
 ('ashlandtheolog141182raus',[14,15,16,17,18]),
 ('ashlandtheologic19124with',[19,20,21,22,23,24]),
 ('ashlandtheologic2530bake',[25,26,27,28,29,30]),
 ('ashlandtheologic3742bake',[37,38,39,40,41,42]),
]
YEARS={7:1974,8:1975,9:1976,10:1977,12:1979,13:1980,14:1981,15:1982,16:1983,17:1984,18:1985,
19:1987,20:1988,21:1989,22:1990,23:1991,24:1992,25:1993,26:1994,27:1995,28:1996,29:1997,30:1998,
37:2005,38:2006,39:2007,40:2008,41:2009,42:2010}

def filename(n):
    title='Ashland Theological Bulletin' if n <= 13 else 'Ashland Theological Journal'
    year=YEARS[n]
    return f'{title} - Volume {n:03d} - {year}.pdf'

def dl(ident,p):
    u=f'https://archive.org/download/{ident}/{ident}.pdf'; last=None
    for k in range(10):
        try:
            r=S.get(u,stream=True,timeout=(30,180),allow_redirects=True)
            if r.status_code==200:
                with open(p,'wb') as f:
                    for b in r.iter_content(1024*1024):
                        if b: f.write(b)
                r.close(); return
            last=f'{r.status_code} {r.url}'; r.close()
        except Exception as e: last=repr(e)
        time.sleep(min(20,2+k*2))
    raise RuntimeError(f'download failed {ident}: {last}')

def norm(t): return re.sub(r'\s+',' ',t.upper().replace('–','-').replace('—','-'))
def has_title(t): return 'ASHLAND' in t and 'THEOLOGICAL' in t and ('JOURNAL' in t or 'BULLETIN' in t)
def contents_hits(texts,y):
    hits=[]
    for i,t in enumerate(texts):
        if has_title(t) and str(y) in t and 'CONTENTS' in t:
            score=100
            if re.search(rf'(SPRING|FALL|AUTUMN|WINTER|SUMMER)[, ]+{y}\b',t): score+=20
            if re.search(r'\bVOL\.?\s*[IVXLCDM]+\b',t) or 'VOLUME' in t: score+=15
            if 'PUBLISHED BY ASHLAND THEOLOGICAL SEMINARY' in t: score+=15
            hits.append((score,i))
    return hits

def locate_cover(texts,n):
    y=YEARS[n]; hits=contents_hits(texts,y)
    if not hits: raise RuntimeError(f'no contents/title hit for volume {n} year {y}')
    mx=max(s for s,_ in hits); c=min(i for s,i in hits if s==mx)
    cand=[j for j in range(max(0,c-8),c+1) if has_title(texts[j]) and str(y) in texts[j]]
    return (min(cand) if cand else c),c,mx

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def main():
    rows=[]
    for old in OUT.glob('*.pdf'): old.unlink()
    with tempfile.TemporaryDirectory(prefix='ashland_upload_') as td:
        td=Path(td)
        for ident,vols in BUNDLES:
            src=td/(ident+'.pdf'); print('BUNDLE_START',ident,vols,flush=True); dl(ident,src)
            doc=fitz.open(src); texts=[norm(doc.load_page(i).get_text('text')) for i in range(doc.page_count)]
            if len(vols)==1:
                n=vols[0]; out=OUT/filename(n); shutil.copy2(src,out)
                r={'volume':n,'year':YEARS[n],'file':out.name,'size_bytes':out.stat().st_size,'size_mib':round(out.stat().st_size/1048576,2),'pages':doc.page_count,'sha256':sha(out)}
                rows.append(r); print('BUILT|'+json.dumps(r),flush=True); doc.close(); continue
            starts={}
            for n in vols: starts[n]=locate_cover(texts,n)[0]
            if list(starts.values())!=sorted(starts.values()) or len(set(starts.values()))!=len(starts): raise RuntimeError(f'bad starts {ident} {starts}')
            for k,n in enumerate(vols):
                st=starts[n]; en=starts[vols[k+1]]-1 if k+1<len(vols) else doc.page_count-1
                out=OUT/filename(n); part=fitz.open(); part.insert_pdf(doc,from_page=st,to_page=en); part.save(out,garbage=4,deflate=True,clean=True); part.close()
                r={'volume':n,'year':YEARS[n],'file':out.name,'size_bytes':out.stat().st_size,'size_mib':round(out.stat().st_size/1048576,2),'pages':en-st+1,'sha256':sha(out)}
                rows.append(r); print('BUILT|'+json.dumps(r),flush=True)
            doc.close()
    rows=sorted(rows,key=lambda x:x['volume'])
    (OUT/'manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print('FINAL_COUNT',len(rows),flush=True)
    if len(rows)!=29: raise SystemExit(f'expected 29, got {len(rows)}')

if __name__=='__main__': main()
