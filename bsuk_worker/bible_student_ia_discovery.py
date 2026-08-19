import json, requests
from pathlib import Path
S=requests.Session(); S.headers.update({'User-Agent':'BSUK Bible Student archival discovery/1.3'})
OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True); BASE='https://archive.org'
queries=[
 'publisher:(Bangalore) AND title:(bible AND student)',
 'publisher:("Scripture Literature Press")',
 'publisher:("Script. Lit. Press")',
 'publisher:("Scripture Lit") AND Bangalore',
 'publisher:("Indian Mission Press") AND Bangalore',
 'title:(bible AND student) AND collection:(digitallibraryindia)',
 'title:(bible AND student) AND collection:(JaiGyan)',
 'description:("Scripture Literature Press")',
 'description:("Indian Mission Press") AND Bangalore',
 '("The Bible Student" AND "Scripture Literature Press")',
 '("The Bible Student" AND Redwood AND year:[1930 TO 1940])',
 '("Bible Student" AND Bangalore AND year:[1930 TO 1940])',
]
fields=['identifier','title','date','year','description','creator','subject','collection','mediatype','language','publisher']
seen={}; sources={}; searches=[]
for q in queries:
    params={'q':q,'rows':500,'page':1,'output':'json','fl[]':fields}
    try:
        r=S.get(BASE+'/advancedsearch.php',params=params,timeout=90); r.raise_for_status(); data=r.json(); docs=data.get('response',{}).get('docs',[])
        searches.append({'query':q,'numFound':data.get('response',{}).get('numFound',0),'returned':len(docs)})
        for d in docs:
            i=d.get('identifier')
            if i: seen.setdefault(i,d); sources.setdefault(i,[]).append(q)
    except Exception as e: searches.append({'query':q,'error':repr(e)})
raw=[{'identifier':i,'queries':sources[i],'doc':d,'item_url':BASE+'/details/'+i} for i,d in seen.items()]
raw.sort(key=lambda x:(str(x['doc'].get('year','')),x['identifier']))
summary={'searches':searches,'unique_hits':len(raw),'hits':[{'identifier':x['identifier'],'title':x['doc'].get('title'),'year':x['doc'].get('year'),'publisher':x['doc'].get('publisher'),'collection':x['doc'].get('collection')} for x in raw[:200]]}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'raw_hits.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
