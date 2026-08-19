import json, re, requests, time
from pathlib import Path

S=requests.Session(); S.headers.update({'User-Agent':'BSUK Bible Student archival discovery/1.1'})
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
seen={}; hit_queries={}; searches=[]
for q in queries:
    params={'q':q,'rows':300,'page':1,'output':'json'}
    for f in fields: params.setdefault('fl[]',[]).append(f)
    try:
        r=S.get(BASE+'/advancedsearch.php',params=params,timeout=90); r.raise_for_status(); data=r.json()
        docs=data.get('response',{}).get('docs',[])
        searches.append({'query':q,'status':r.status_code,'numFound':data.get('response',{}).get('numFound',0),'returned':len(docs)})
        for d in docs:
            ident=d.get('identifier')
            if not ident: continue
            if ident not in seen: seen[ident]=d
            hit_queries.setdefault(ident,[]).append(q)
    except Exception as e:
        searches.append({'query':q,'error':repr(e)})

def text(v):
    if isinstance(v,list): return ' '.join(map(str,v))
    return str(v or '')

def score(d,ident):
    title=text(d.get('title')).lower(); desc=text(d.get('description')).lower(); creator=text(d.get('creator')).lower(); subj=text(d.get('subject')).lower(); pub=text(d.get('publisher')).lower(); ident_l=ident.lower()
    alltxt=' '.join([title,desc,creator,subj,pub,ident_l])
    s=0
    if 'bible student' in title: s+=6
    elif 'bible' in title and 'student' in title: s+=4
    if 'biblestudent' in ident_l or 'bible_student' in ident_l: s+=4
    if 'alfred' in alltxt and 'redwood' in alltxt: s+=6
    elif 'redwood' in alltxt: s+=4
    if 'mysore' in alltxt: s+=5
    if 'bangalore' in alltxt: s+=4
    if 'india' in alltxt: s+=1
    y=text(d.get('year') or d.get('date'))
    if re.search(r'19(3\d|4\d|5\d|60)',y): s+=1
    return s

raw=[]
for ident,d in seen.items():
    raw.append({'identifier':ident,'score':score(d,ident),'queries':hit_queries.get(ident,[]),'doc':d})
raw.sort(key=lambda x:(-x['score'],x['identifier']))
(OUT/'raw_hits.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')

# Fetch metadata for every Redwood hit and the strongest title/identifier candidates.
selected=[]
for r in raw:
    qtext=' '.join(r['queries']).lower()
    if r['score']>=4 or 'redwood' in qtext:
        selected.append(r)
    if len(selected)>=180: break

candidates=[]
for r in selected:
    ident=r['identifier']; d=r['doc']
    rec={'search_doc':d,'score':r['score'],'queries':r['queries'],'identifier':ident,'item_url':BASE+'/details/'+ident,'pdf_files':[],'metadata':{}}
    try:
        rr=S.get(BASE+'/metadata/'+ident,timeout=90); rr.raise_for_status(); md=rr.json()
        meta=md.get('metadata',{}) or {}
        rec['metadata']={k:meta.get(k) for k in ['title','date','year','description','creator','subject','collection','identifier','publicdate','publisher','language'] if k in meta}
        for f in md.get('files',[]):
            name=f.get('name',''); fmt=text(f.get('format')).lower()
            if name.lower().endswith('.pdf') or 'pdf' in fmt:
                rec['pdf_files'].append({'name':name,'size':f.get('size'),'format':f.get('format'),'source':f.get('source'),'url':BASE+'/download/'+ident+'/'+requests.utils.quote(name,safe='')})
    except Exception as e:
        rec['metadata_error']=repr(e)
    candidates.append(rec); time.sleep(0.08)

summary={'searches':searches,'unique_search_hits':len(seen),'raw_top_score':raw[0]['score'] if raw else 0,'candidates':len(candidates),'candidates_with_pdf':sum(bool(x['pdf_files']) for x in candidates)}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
for c in candidates[:100]:
    print('\nSCORE',c['score'],'ID',c['identifier'],'TITLE',text(c.get('metadata',{}).get('title') or c['search_doc'].get('title')),'PDFS',len(c['pdf_files']))
    print('Q',c['queries'])
