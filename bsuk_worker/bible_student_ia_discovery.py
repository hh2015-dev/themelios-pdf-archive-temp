import json, requests
from pathlib import Path

S=requests.Session(); S.headers.update({'User-Agent':'BSUK Bible Student archival discovery/1.2'})
OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True)
BASE='https://archive.org'
queries=[
 'title:(bible AND student) AND year:[1930 TO 1960]',
 'title:("The Bible Student")',
 'identifier:biblestudent*',
 'identifier:bible_student*',
 'creator:(Redwood)',
 'description:(Redwood)',
 '"Alfred McDonald Redwood"',
 '("Bible Student" AND Mysore)',
 '("Bible Student" AND Bangalore)',
 '("Bible Student" AND India AND year:[1930 TO 1960])',
 '(Mysore AND Redwood)',
 '(Bangalore AND Redwood)',
]
fields=['identifier','title','date','year','description','creator','subject','collection','mediatype','language','publisher']
seen={}; sources={}; searches=[]
for q in queries:
    params={'q':q,'rows':300,'page':1,'output':'json','fl[]':fields}
    try:
        r=S.get(BASE+'/advancedsearch.php',params=params,timeout=90); r.raise_for_status(); data=r.json(); docs=data.get('response',{}).get('docs',[])
        searches.append({'query':q,'numFound':data.get('response',{}).get('numFound',0),'returned':len(docs)})
        for d in docs:
            ident=d.get('identifier')
            if ident:
                seen.setdefault(ident,d); sources.setdefault(ident,[]).append(q)
    except Exception as e: searches.append({'query':q,'error':repr(e)})

def text(v): return ' '.join(map(str,v)) if isinstance(v,list) else str(v or '')
def score(d,ident):
    title=text(d.get('title')).lower(); alltxt=' '.join(text(d.get(k)) for k in fields).lower()+' '+ident.lower(); s=0
    if 'bible student' in title:s+=6
    elif 'bible' in title and 'student' in title:s+=4
    if 'biblestudent' in ident.lower() or 'bible_student' in ident.lower():s+=4
    if 'redwood' in alltxt:s+=4
    if 'alfred' in alltxt and 'redwood' in alltxt:s+=2
    if 'mysore' in alltxt:s+=5
    if 'bangalore' in alltxt:s+=4
    if 'india' in alltxt:s+=1
    return s
raw=[{'identifier':i,'score':score(d,i),'queries':sources[i],'doc':d,'item_url':BASE+'/details/'+i} for i,d in seen.items()]
raw.sort(key=lambda x:(-x['score'],x['identifier']))
summary={'searches':searches,'unique_hits':len(raw),'top_scores':[{'score':x['score'],'identifier':x['identifier'],'title':x['doc'].get('title')} for x in raw[:30]]}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'raw_hits.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
