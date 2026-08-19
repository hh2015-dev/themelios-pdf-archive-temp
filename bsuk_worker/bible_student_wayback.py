import hashlib, json, time, requests
from pathlib import Path
from pypdf import PdfReader

OUT=Path('bible_student_wayback'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK archival recovery/1.1'})
targets=[
 ('v19_i1_missing','bible-student_19-1_042.pdf'),
 ('v20_i2_conflict','bible-student_20-2_089.pdf'),
 ('v21_i1_missing','bible-student_21-1_042.pdf'),
]
rows=[]
for label,fn in targets:
 rec={'label':label,'filename':fn,'queries':[],'availability':[],'captures':[]}
 path='/pdf/bible-student/'+fn
 variants=[
  'https://www.biblicalstudies.org.uk'+path,
  'http://www.biblicalstudies.org.uk'+path,
  'https://biblicalstudies.org.uk'+path,
  'http://biblicalstudies.org.uk'+path,
  'www.biblicalstudies.org.uk'+path,
  'biblicalstudies.org.uk'+path,
 ]
 seen=set()
 for orig in variants:
  try:
   ar=S.get('https://archive.org/wayback/available',params={'url':orig},timeout=60)
   av={'original_query':orig,'status':ar.status_code,'bytes':len(ar.content)}
   try: av['data']=ar.json()
   except Exception: av['text']=ar.text[:1000]
   rec['availability'].append(av)
  except Exception as e: rec['availability'].append({'original_query':orig,'error':repr(e)})
  params={'url':orig,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest,length','filter':'statuscode:200','collapse':'digest'}
  for attempt in range(3):
   try:
    r=S.get('https://web.archive.org/cdx/search/cdx',params=params,timeout=90)
    q={'original_query':orig,'attempt':attempt+1,'url':r.url,'status':r.status_code,'bytes':len(r.content)}
    if r.status_code==503 and attempt<2:
     rec['queries'].append(q); time.sleep(3*(attempt+1)); continue
    try:data=r.json();q['rows']=max(0,len(data)-1)
    except Exception:data=[];q['text']=r.text[:1000]
    rec['queries'].append(q)
    if isinstance(data,list) and len(data)>1:
     hdr=data[0]
     for vals in data[1:]:
      d=dict(zip(hdr,vals)); sig=(d.get('timestamp'),d.get('original'))
      if sig not in seen: seen.add(sig); rec['captures'].append(d)
    break
   except Exception as e:
    rec['queries'].append({'original_query':orig,'attempt':attempt+1,'error':repr(e)})
    if attempt<2: time.sleep(3*(attempt+1))
 valid=[]; digests=set()
 for cap in sorted(rec['captures'],key=lambda x:x.get('timestamp',''),reverse=True)[:30]:
  ts=cap.get('timestamp'); original=cap.get('original'); wb='https://web.archive.org/web/'+ts+'id_/'+original
  info=dict(cap); info['wayback_url']=wb
  try:
   rr=S.get(wb,timeout=120,allow_redirects=True); data=rr.content
   info.update({'fetch_status':rr.status_code,'final_url':rr.url,'bytes_fetched':len(data),'pdf_magic':data.startswith(b'%PDF-')})
   if data.startswith(b'%PDF-'):
    sha=hashlib.sha256(data).hexdigest(); info['sha256']=sha
    if sha not in digests:
     digests.add(sha); p=OUT/(label+'_'+ts+'_'+sha[:10]+'.pdf'); p.write_bytes(data)
     try: info['pages']=len(PdfReader(str(p)).pages); info['saved_as']=p.name
     except Exception as e: info['pdf_read_error']=repr(e)
     valid.append(info)
  except Exception as e: info['fetch_error']=repr(e)
 rec['valid_pdfs']=valid
 rows.append(rec)
(OUT/'summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'label':r['label'],'captures':len(r['captures']),'valid_pdfs':len(r['valid_pdfs']),'availability_snapshots':sum(1 for a in r['availability'] if isinstance(a.get('data'),dict) and a['data'].get('archived_snapshots'))} for r in rows],ensure_ascii=False,indent=2))
