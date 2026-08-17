import csv, hashlib, json, os, re, tempfile, time
from pathlib import Path
from urllib.parse import quote
import fitz
import requests

META='https://archive.org/metadata/{id}'
DL='https://archive.org/download/{id}/{name}'
OUT=Path('ashland_inventory_v3'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers['User-Agent']='BSUK-Ashland-Inventory/3.0'

# Archive bundles are fixed here to prevent search/metadata parsing ambiguity.
BUNDLES=[
 ('ashlandtheologic1161alde',1,6),
 ('ashlandtheologic71121alde',7,12),
 ('ashlandtheologic131kick',13,13),
 ('ashlandtheolog141182raus',14,18),
 ('ashlandtheologic19124with',19,24),
 ('ashlandtheologic2530bake',25,30),
 ('ashlandtheologic3136bake',31,36),
 ('ashlandtheologic3742bake',37,42),
]
# Opening year for each volume. Volume 18 starts in 1985 and contains its later No.2 as part of the same volume.
YEARS={
 1:1968,2:1969,3:1970,4:1971,5:1972,6:1973,
 7:1974,8:1975,9:1976,10:1977,11:1978,12:1979,13:1980,
 14:1981,15:1982,16:1983,17:1984,18:1985,
 19:1987,20:1988,21:1989,22:1990,23:1991,24:1992,
 25:1993,26:1994,27:1995,28:1996,29:1997,30:1998,
 31:1999,32:2000,33:2001,34:2002,35:2003,36:2004,
 37:2005,38:2006,39:2007,40:2008,41:2009,42:2010,
}

def gj(url):
 err=None
 for k in range(5):
  try:
   r=S.get(url,timeout=90); r.raise_for_status(); return r.json()
  except Exception as e: err=e; time.sleep(2**k)
 raise RuntimeError(f'GET failed {url}: {err}')

def down(url,p):
 err=None
 for k in range(4):
  try:
   with S.get(url,stream=True,timeout=(30,180)) as r:
    r.raise_for_status()
    with open(p,'wb') as f:
     for b in r.iter_content(1024*1024):
      if b:f.write(b)
   return
  except Exception as e:
   err=e
   try:os.remove(p)
   except OSError:pass
   time.sleep(3*(k+1))
 raise RuntimeError(f'download failed {url}: {err}')

def pick_pdf(files,ident):
 c=[]
 for f in files:
  n=f.get('name',''); fmt=str(f.get('format','')); sz=int(f.get('size') or 0)
  if not n.lower().endswith('.pdf'):continue
  sc=0
  if n==ident+'.pdf':sc+=1000
  if 'Text PDF' in fmt:sc+=500
  if f.get('source')=='derivative':sc+=20
  if '_bw.pdf' in n.lower():sc-=200
  c.append((sc,sz,n,fmt))
 if not c:return None
 return sorted(c,reverse=True)[0]

def norm(t):return re.sub(r'\s+',' ',t.upper().replace('–','-').replace('—','-'))
def has_title(t):return 'ASHLAND' in t and 'THEOLOGICAL' in t and ('JOURNAL' in t or 'BULLETIN' in t)

def year_score(t,y):
 if not has_title(t) or str(y) not in t:return 0
 s=20
 # The volume opening pages characteristically contain one or more of these.
 if 'CONTENTS' in t:s+=80
 if re.search(rf'ASHLAND\s*,?\s+OHIO\s+{y}\b',t):s+=70
 if re.search(rf'(?:JOURNAL|BULLETIN)\s+{y}\b',t):s+=50
 if 'ISSN' in t:s+=15
 if 'PUBLISHED' in t or 'COPYRIGHT' in t:s+=10
 return s

def roman(n):
 vals=[(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')];s=''
 for v,z in vals:
  while n>=v:s+=z;n-=v
 return s

def ed(a,b):
 p=list(range(len(b)+1))
 for i,ca in enumerate(a,1):
  q=[i]
  for j,cb in enumerate(b,1):q.append(min(q[-1]+1,p[j]+1,p[j-1]+(ca!=cb)))
  p=q
 return p[-1]

def volume_marker_score(t,n):
 if not has_title(t):return 0
 target=roman(n); best=0
 if re.search(rf'ASHLAND\s+THEOLOGICAL\s+(?:JOURNAL|BULLETIN)\s+0*{n}\b',t):best=70
 for tok in re.findall(r'\bVOLUME\s+([IVXL1]{1,8})\b',t):
  tok=tok.replace('1','I');d=ed(tok,target)
  if d==0:best=max(best,100+(20 if 'CONTENTS' in t else 0))
  elif d==1 and len(target)>=3:best=max(best,90+(20 if 'CONTENTS' in t else 0))
 return best

def locate_year_start(texts,n):
 y=YEARS[n]
 hits=[(year_score(t,y),i) for i,t in enumerate(texts) if year_score(t,y)>0]
 if hits:
  mx=max(s for s,_ in hits)
  # Opening cover/title page should be the first page among the strongest candidates.
  return min(i for s,i in hits if s==mx),mx,'year'
 # Fallback to volume marker if year OCR is unusable.
 mh=[(volume_marker_score(t,n),i) for i,t in enumerate(texts) if volume_marker_score(t,n)>0]
 if mh:
  mx=max(s for s,_ in mh);m=min(i for s,i in mh if s==mx)
  # Backtrack to earliest nearby journal-title page.
  c=[j for j in range(max(0,m-12),m+1) if has_title(texts[j])]
  return (min(c) if c else m),mx,'volume-marker'
 raise RuntimeError(f'cannot locate opening for volume {n} year {y}')

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def write(rows,errors):
 rows=sorted(rows,key=lambda r:r['volume'])
 (OUT/'inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 (OUT/'errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
 if rows:
  with open(OUT/'inventory.csv','w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 with open(OUT/'inventory.md','w',encoding='utf-8') as f:
  f.write('| Volume | Opening year | MiB | Bytes | Pages | Bundle |\n|---:|---:|---:|---:|---:|---|\n')
  for r in rows:f.write(f"| {r['volume']} | {r['year']} | {r['size_mib']:.2f} | {r['size_bytes']} | {r['pages']} | {r['bundle_identifier']} |\n")

def main():
 rows=[];errors=[]
 with tempfile.TemporaryDirectory(prefix='ashland_v3_') as td:
  td=Path(td)
  for ident,a,b in BUNDLES:
   src=td/(ident+'.pdf')
   try:
    meta=gj(META.format(id=ident)); p=pick_pdf(meta.get('files',[]),ident)
    if not p:raise RuntimeError('no downloadable PDF')
    _,meta_sz,name,fmt=p
    print(f'BUNDLE_META|{a}-{b}|{ident}|{name}|{meta_sz}|{fmt}',flush=True)
    down(DL.format(id=quote(ident),name=quote(name)),src);actual=src.stat().st_size
    print(f'BUNDLE_DOWNLOADED|{ident}|{actual}',flush=True)
    doc=fitz.open(src);texts=[norm(doc.load_page(i).get_text('text')) for i in range(doc.page_count)]
    starts={};methods={};scores={}
    for n in range(a,b+1):
     st,sc,method=locate_year_start(texts,n);starts[n]=st;scores[n]=sc;methods[n]=method
    pp=[starts[n] for n in range(a,b+1)]
    if pp!=sorted(pp) or len(set(pp))!=len(pp):raise RuntimeError(f'non-monotonic year starts {starts}')
    print('BOUNDARIES|'+ident+'|'+json.dumps({'starts':starts,'years':{n:YEARS[n] for n in range(a,b+1)},'methods':methods,'scores':scores}),flush=True)
    vols=list(range(a,b+1))
    for k,n in enumerate(vols):
     st=starts[n];en=starts[vols[k+1]]-1 if k+1<len(vols) else doc.page_count-1
     if en<st:raise RuntimeError(f'bad range {n}: {st}-{en}')
     out=td/f'Ashland_Theological_Volume_{n:02d}.pdf';part=fitz.open();part.insert_pdf(doc,from_page=st,to_page=en);part.save(out,garbage=4,deflate=True,clean=True);part.close()
     sz=out.stat().st_size;r={'volume':n,'year':YEARS[n],'size_bytes':sz,'size_mib':round(sz/1048576,2),'pages':en-st+1,'bundle_identifier':ident,'source_pdf':name,'source_pdf_bytes':actual,'start_page_1based':st+1,'end_page_1based':en+1,'boundary_method':methods[n],'boundary_score':scores[n],'sha256':sha(out)}
     rows.append(r);print(f"RESULT|{n}|{YEARS[n]}|{sz}|{r['size_mib']:.2f}|{r['pages']}|{ident}|{st+1}-{en+1}|{methods[n]}|{scores[n]}|{r['sha256']}",flush=True);out.unlink();write(rows,errors)
    doc.close();src.unlink();print('BUNDLE_DONE|'+ident,flush=True)
   except Exception as e:
    errors.append({'identifier':ident,'range':[a,b],'error':repr(e)});print(f'BUNDLE_ERROR|{ident}|{repr(e)}',flush=True)
    try:src.unlink()
    except OSError:pass
    write(rows,errors)
 write(rows,errors);vs=sorted(r['volume'] for r in rows)
 print('FINAL_VOLUMES='+json.dumps(vs),flush=True);print('FINAL_COUNT='+str(len(vs)),flush=True);print('ERRORS='+json.dumps(errors),flush=True)
 if vs!=list(range(1,43)) or errors:raise SystemExit(2)

if __name__=='__main__':main()
