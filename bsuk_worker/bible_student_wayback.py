import hashlib, json, re, requests
from pathlib import Path
from urllib.parse import urlsplit
from pypdf import PdfReader

OUT=Path('bible_student_wayback'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK archival recovery/1.0'})
targets=[
 ('v19_i1_missing','bible-student_19-1_042.pdf'),
 ('v20_i2_conflict','bible-student_20-2_089.pdf'),
 ('v21_i1_missing','bible-student_21-1_042.pdf'),
]
rows=[]
for label,fn in targets:
 rec={'label':label,'filename':fn,'queries':[],'captures':[]}
 hosts=['www.biblicalstudies.org.uk','biblicalstudies.org.uk']
 seen=set()
 for host in hosts:
  orig='https://'+host+'/pdf/bible-student/'+fn
  params={'url':orig,'output':'json','fl':'timestamp,original,statuscode,mimetype,digest,length','filter':'statuscode:200','collapse':'digest'}
  try:
   r=S.get('https://web.archive.org/cdx/search/cdx',params=params,timeout=90)
   q={'url':r.url,'status':r.status_code,'bytes':len(r.content)}
   try:data=r.json();q['rows']=max(0,len(data)-1)
   except Exception:data=[];q['text']=r.text[:1000]
   rec['queries'].append(q)
   if isinstance(data,list) and len(data)>1:
    hdr=data[0]
    for vals in data[1:]:
     d=dict(zip(hdr,vals)); sig=(d.get('timestamp'),d.get('original'))
     if sig not in seen: seen.add(sig); rec['captures'].append(d)
  except Exception as e:rec['queries'].append({'host':host,'error':repr(e)})
 # Fetch each unique capture, newest first; retain differing valid PDFs.
 valid=[]; digests=set()
 for cap in sorted(rec['captures'],key=lambda x:x.get('timestamp',''),reverse=True)[:20]:
  ts=cap.get('timestamp'); original=cap.get('original')
  wb='https://web.archive.org/web/'+ts+'id_/'+original
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
  except Exception as e:info['fetch_error']=repr(e)
 rec['valid_pdfs']=valid
 rows.append(rec)
(OUT/'summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'label':r['label'],'captures':len(r['captures']),'valid_pdfs':len(r['valid_pdfs']),'queries':r['queries']} for r in rows],ensure_ascii=False,indent=2))
