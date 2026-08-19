import json, requests
from pathlib import Path
OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK Bible Student archival discovery/1.6'})
URL='https://archive.org/services/search/beta/page_production/'
queries=[
 '"The Bible Student" "A. McD. Redwood"',
 '"The Bible Student" "A. McDonald Redwood"',
 '"The Bible Student" "McD. Redwood" Bangalore',
 '"The Bible Student" Redwood "Cavalry Road"',
 '"The Bible Student" Redwood "Scripture Literature Press" Bangalore',
 '"Published by Mr. A. McD. Redwood"',
 '"Editor, The Bible Student" Bangalore India',
 '"Editor of The Bible Student" Bangalore',
 '"The Bible Student" "Volume IX" Redwood',
 '"The Bible Student" "Vol. IX" Redwood',
 '"The Bible Student" "Volume X" Redwood',
 '"The Bible Student" "Volume XI" Redwood',
 '"The Bible Student" "Volume XII" Redwood',
 '"The Bible Student" "Volume XIII" Redwood',
 '"The Bible Student" "Volume XIV" Redwood',
 '"The Bible Student" "Volume XV" Redwood',
 '"The Bible Student" "Volume XVI" Redwood',
 '"The Bible Student" "Volume XVII" Redwood',
 '"The Bible Student" "Volume XVIII" Redwood',
]
results=[]
for q in queries:
 rec={'query':q}
 try:
  r=S.get(URL,params={'service_backend':'fts','user_query':q,'hits_per_page':100,'page':1,'aggregations':'false'},timeout=90)
  rec['status']=r.status_code; rec['bytes']=len(r.content); rec['data']=r.json()
 except Exception as e: rec['error']=repr(e)
 results.append(rec)
(OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'query':x['query'],'status':x.get('status'),'bytes':x.get('bytes'),'hits':len(x.get('data',{}).get('response',{}).get('body',{}).get('hits',{}).get('hits',[]))} for x in results],ensure_ascii=False,indent=2))
