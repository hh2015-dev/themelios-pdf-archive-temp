import json, re, requests, sys, time
from pathlib import Path

S=requests.Session(); S.headers.update({'User-Agent':'BSUK Bible Student archival discovery/1.0'})
OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True)
BASE='https://archive.org'
queries=[
    'title:("The Bible Student") AND year:[1930 TO 1960]',
    'title:("Bible Student") AND (Mysore OR Bangalore)',
    'description:("Bible Student") AND (Mysore OR Bangalore)',
    'creator:(Redwood) AND (Bible OR Christian)',
    'subject:("Bible Student") AND (India OR Mysore OR Bangalore)',
]
fields=['identifier','title','date','year','description','creator','subject','collection','mediatype']
seen={}; searches=[]
for q in queries:
    params={'q':q,'rows':200,'page':1,'output':'json'}
    for f in fields: params.setdefault('fl[]',[]).append(f)
    try:
        r=S.get(BASE+'/advancedsearch.php',params=params,timeout=90); r.raise_for_status(); data=r.json()
        docs=data.get('response',{}).get('docs',[]); searches.append({'query':q,'status':r.status_code,'numFound':data.get('response',{}).get('numFound',0),'returned':len(docs)})
        for d in docs:
            ident=d.get('identifier')
            if ident: seen[ident]=d
    except Exception as e:
        searches.append({'query':q,'error':repr(e)})

# Fetch metadata only for candidates with meaningful lexical overlap.
def text(v):
    if isinstance(v,list): return ' '.join(map(str,v))
    return str(v or '')

def score(d):
    t=' '.join(text(d.get(k)) for k in ['title','description','creator','subject']).lower()
    s=0
    if 'bible student' in t: s+=4
    if 'mysore' in t: s+=4
    if 'bangalore' in t: s+=3
    if 'redwood' in t: s+=3
    if 'india' in t: s+=1
    return s

candidates=[]
for ident,d in sorted(seen.items(), key=lambda kv: score(kv[1]), reverse=True):
    if score(d)<4: continue
    rec={'search_doc':d,'score':score(d),'identifier':ident,'item_url':BASE+'/details/'+ident,'pdf_files':[],'metadata':{}}
    try:
        rr=S.get(BASE+'/metadata/'+ident,timeout=90); rr.raise_for_status(); md=rr.json()
        meta=md.get('metadata',{}) or {}; rec['metadata']={k:meta.get(k) for k in ['title','date','year','description','creator','subject','collection','identifier','publicdate'] if k in meta}
        for f in md.get('files',[]):
            name=f.get('name',''); fmt=text(f.get('format')).lower(); source=text(f.get('source')).lower()
            if name.lower().endswith('.pdf') or 'pdf' in fmt:
                rec['pdf_files'].append({'name':name,'size':f.get('size'),'format':f.get('format'),'source':f.get('source'),'url':BASE+'/download/'+ident+'/'+requests.utils.quote(name,safe='')})
    except Exception as e:
        rec['metadata_error']=repr(e)
    candidates.append(rec)
    time.sleep(0.15)

summary={'searches':searches,'unique_search_hits':len(seen),'candidates':len(candidates),'candidates_with_pdf':sum(bool(x['pdf_files']) for x in candidates)}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
for c in candidates[:60]:
    print('\n',c['score'],c['identifier'],text(c.get('metadata',{}).get('title') or c['search_doc'].get('title')), 'PDFS',len(c['pdf_files']))
