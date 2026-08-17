import json, os, re, tempfile, time, hashlib
from pathlib import Path
import requests, fitz
S=requests.Session(); S.headers['User-Agent']='BSUK-Ashland-FinalMeasure/8.0'
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

def dl(ident,p):
 u=f'https://archive.org/download/{ident}/{ident}.pdf';last=None
 for k in range(10):
  try:
   r=S.get(u,stream=True,timeout=(30,180),allow_redirects=True)
   if r.status_code==200:
    with open(p,'wb') as f:
     for b in r.iter_content(1024*1024):
      if b:f.write(b)
    r.close();return
   last=f'{r.status_code} {r.url}';r.close()
  except Exception as e:last=repr(e)
  time.sleep(min(20,2+k*2))
 raise RuntimeError(f'download failed {ident}: {last}')

def norm(t):return re.sub(r'\s+',' ',t.upper().replace('–','-').replace('—','-'))
def title(t):return 'ASHLAND' in t and 'THEOLOGICAL' in t and ('JOURNAL' in t or 'BULLETIN' in t)
def contents_hits(texts,y):
 hits=[]
 for i,t in enumerate(texts):
  if title(t) and str(y) in t and 'CONTENTS' in t:
   score=100
   if re.search(rf'(SPRING|FALL|AUTUMN|WINTER|SUMMER)[, ]+{y}\b',t):score+=20
   if re.search(r'\bVOL\.?\s*[IVXLCDM]+\b',t) or 'VOLUME' in t:score+=15
   if 'PUBLISHED BY ASHLAND THEOLOGICAL SEMINARY' in t:score+=15
   hits.append((score,i))
 return hits

def locate_cover(texts,n):
 y=YEARS[n];hits=contents_hits(texts,y)
 if not hits:raise RuntimeError(f'no contents/title hit for volume {n} year {y}')
 mx=max(s for s,_ in hits); c=min(i for s,i in hits if s==mx)
 # Walk back through the local front-matter cluster. Prefer earliest title-bearing page carrying same year.
 cand=[]
 for j in range(max(0,c-8),c+1):
  t=texts[j]
  if title(t) and str(y) in t:cand.append(j)
 start=min(cand) if cand else c
 return start,c,mx

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 rows=[]
 with tempfile.TemporaryDirectory(prefix='ashland_final_v8_') as td:
  td=Path(td)
  for ident,vols in BUNDLES:
   src=td/(ident+'.pdf'); print('BUNDLE_START',ident,vols,flush=True); dl(ident,src)
   src_size=src.stat().st_size; doc=fitz.open(src); texts=[norm(doc.load_page(i).get_text('text')) for i in range(doc.page_count)]
   if len(vols)==1:
    n=vols[0]
    r={'volume':n,'year':YEARS[n],'size_bytes':src_size,'size_mib':round(src_size/1048576,2),'pages':doc.page_count,'start_page':1,'end_page':doc.page_count,'bundle':ident,'method':'original-single-volume','sha256':sha(src)}
    rows.append(r);print('FINAL|'+json.dumps(r),flush=True);doc.close();src.unlink();continue
   starts={};contents={}
   for n in vols:
    st,ct,sc=locate_cover(texts,n);starts[n]=st;contents[n]=ct
   if list(starts.values())!=sorted(starts.values()) or len(set(starts.values()))!=len(starts):raise RuntimeError(f'bad starts {ident} {starts}')
   print('STARTS|'+ident+'|'+json.dumps({'starts_1based':{n:s+1 for n,s in starts.items()},'contents_1based':{n:c+1 for n,c in contents.items()}}),flush=True)
   for k,n in enumerate(vols):
    st=starts[n];en=starts[vols[k+1]]-1 if k+1<len(vols) else doc.page_count-1
    if en<st:raise RuntimeError(f'bad range {n}')
    out=td/f'vol{n:02d}.pdf';part=fitz.open();part.insert_pdf(doc,from_page=st,to_page=en);part.save(out,garbage=4,deflate=True,clean=True);part.close()
    sz=out.stat().st_size
    r={'volume':n,'year':YEARS[n],'size_bytes':sz,'size_mib':round(sz/1048576,2),'pages':en-st+1,'start_page':st+1,'end_page':en+1,'bundle':ident,'method':'cover-to-before-next-cover','sha256':sha(out)}
    rows.append(r);print('FINAL|'+json.dumps(r),flush=True);out.unlink()
   doc.close();src.unlink()
 print('ALL_ROWS|'+json.dumps(sorted(rows,key=lambda x:x['volume'])),flush=True)
 print('COUNT',len(rows),flush=True)
if __name__=='__main__':main()
