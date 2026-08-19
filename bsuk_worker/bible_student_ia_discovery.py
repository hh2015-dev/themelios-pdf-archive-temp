import json,re,requests
from pathlib import Path
from urllib.parse import unquote
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK Bible Student archival discovery/1.4'})
OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True); BASE='https://archive.org'
queries=[
 '"The Bible Student" "Alfred McDonald Redwood"',
 '"The Bible Student" Mysore',
 '"The Bible Student" Bangalore',
 '"Recent Finds in Palestine"',
 '"Exegetical Study of Colossians" "Bible Student"',
 '"The Bible Student" "Scripture Literature Press"',
 '"The Bible Student" Redwood 1936',
 '"The Bible Student" Redwood 1939',
 '"The Bible Student" Redwood 1940',
]
results=[]
for q in queries:
    rec={'query':q,'status':None,'url':None,'identifiers':[],'bytes':0}
    try:
        r=S.get(BASE+'/search.php',params={'query':q,'sin':'TXT'},timeout=90,allow_redirects=True)
        rec['status']=r.status_code; rec['url']=r.url; rec['bytes']=len(r.content)
        html=r.text
        ids=[]
        for m in re.finditer(r'href=["\'](?:https://archive\.org)?/details/([^?/#"\']+)',html,re.I):
            ident=unquote(m.group(1))
            if ident not in ids: ids.append(ident)
        rec['identifiers']=ids[:100]
        rec['sample']=re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',html))[:2500]
    except Exception as e: rec['error']=repr(e)
    results.append(rec)
summary={'queries':results,'unique_identifiers':sorted({i for r in results for i in r.get('identifiers',[])})}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
