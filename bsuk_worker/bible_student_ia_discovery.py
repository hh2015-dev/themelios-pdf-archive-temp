import gzip, json, re, requests
from pathlib import Path
from urllib.parse import quote
OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK Bible Student archival discovery/1.7'})
ids=[
 'clippingsmimeogr00uns_xll',
 'karnataka-state-archives-RGVlcGFrMTU0MjM1-RGVlcGFrMQ',
 'karnataka-state-archives-RGVlcGFrMTU0ODQ3-RGVlcGFrMQ',
 'karnataka-state-archives-2026-408464',
]
results=[]
for ident in ids:
 rec={'identifier':ident,'metadata':{},'candidate_files':[],'contexts':[]}
 try:
  mr=S.get('https://archive.org/metadata/'+ident,timeout=90); mr.raise_for_status(); md=mr.json(); rec['metadata']=md.get('metadata',{})
  files=md.get('files',[])
  for f in files:
   name=f.get('name',''); low=name.lower(); fmt=str(f.get('format','')).lower()
   if low.endswith('.pdf') or low.endswith('.txt') or low.endswith('.txt.gz') or 'text pdf' in fmt or 'search text' in fmt:
    rec['candidate_files'].append({'name':name,'size':f.get('size'),'format':f.get('format'),'source':f.get('source')})
  # Prefer OCR/search text under 100 MB.
  textfiles=[]
  for f in files:
   n=f.get('name',''); size=int(f.get('size') or 0)
   if size>100_000_000: continue
   if n.lower().endswith(('_djvu.txt','_hocr_searchtext.txt.gz','_searchtext.txt.gz','.txt')):
    textfiles.append((0 if 'searchtext' in n.lower() else 1,n,size))
  textfiles.sort()
  for _,name,size in textfiles[:4]:
   try:
    u='https://archive.org/download/'+ident+'/'+quote(name,safe='')
    rr=S.get(u,timeout=120); rr.raise_for_status(); b=rr.content
    if name.lower().endswith('.gz'): b=gzip.decompress(b)
    txt=b.decode('utf-8','replace')
    # store local OCR sample for downstream inspection
    safe=re.sub(r'[^A-Za-z0-9._-]+','_',ident+'__'+name)[-180:]
    (OUT/safe).write_text(txt,encoding='utf-8',errors='replace')
    for pat in [r'the\s+bible\s+student',r'a\.?\s*mcd\.?\s*redwood',r'alfred\s+mcdonald\s+redwood',r'scripture\s+literature\s+press']:
     for m in list(re.finditer(pat,txt,re.I))[:30]:
      a=max(0,m.start()-1200); z=min(len(txt),m.end()+1800)
      rec['contexts'].append({'file':name,'pattern':pat,'offset':m.start(),'context':re.sub(r'\s+',' ',txt[a:z])})
   except Exception as e: rec.setdefault('text_errors',[]).append({'file':name,'error':repr(e)})
 except Exception as e: rec['error']=repr(e)
 results.append(rec)
(OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'identifier':r['identifier'],'title':r.get('metadata',{}).get('title'),'files':len(r.get('candidate_files',[])),'contexts':len(r.get('contexts',[])),'error':r.get('error')} for r in results],ensure_ascii=False,indent=2))
