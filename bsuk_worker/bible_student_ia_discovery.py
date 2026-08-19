import json, requests
from pathlib import Path
OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK Bible Student archival discovery/1.5'})
URL='https://archive.org/services/search/beta/page_production/'
queries=[
 '"Recent Finds in Palestine"',
 '"Exegetical Study of Colossians"',
 '"Exegetical Study of Colossians" "verse 9"',
 '"The Bible Student" "Alfred McDonald Redwood"',
 '"The Bible Student" Redwood',
 '"The Bible Student" Mysore',
 '"The Bible Student" Bangalore',
 '"The Bible Student" "Scripture Literature Press"',
 '"The Bible Student" "Indian Mission Press"',
 '"The Bible Student" 1931',
 '"The Bible Student" 1932',
 '"The Bible Student" 1933',
 '"The Bible Student" 1934',
 '"The Bible Student" 1935',
 '"The Bible Student" 1936',
 '"The Bible Student" 1937',
 '"The Bible Student" 1938',
 '"The Bible Student" 1939',
 '"The Bible Student" 1940',
]
results=[]
for q in queries:
    rec={'query':q}
    try:
        r=S.get(URL,params={'service_backend':'fts','user_query':q,'hits_per_page':100,'page':1,'aggregations':'false'},timeout=90)
        rec['status']=r.status_code; rec['url']=r.url; rec['content_type']=r.headers.get('content-type'); rec['bytes']=len(r.content)
        try: rec['data']=r.json()
        except Exception: rec['text']=r.text[:5000]
    except Exception as e: rec['error']=repr(e)
    results.append(rec)
(OUT/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'query':x['query'],'status':x.get('status'),'bytes':x.get('bytes'),'keys':list(x.get('data',{}).keys()) if isinstance(x.get('data'),dict) else None} for x in results],ensure_ascii=False,indent=2))
