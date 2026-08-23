import requests,json,urllib.parse
from concurrent.futures import ThreadPoolExecutor,as_completed
BASE='https://archive.org'
qs=[
'collection:graduatetheologicalunion AND (hebrew OR aramaic OR syriac) AND year:[1700 TO 1899]',
'collection:graduatetheologicalunion AND (hebrew OR aramaic OR syriac) AND year:[1900 TO 1975]',
'collection:graduatetheologicalunion AND (septuagint OR greek OR textual OR manuscript) AND year:[1800 TO 1925]',
'collection:graduatetheologicalunion AND (septuagint OR greek OR textual OR manuscript) AND year:[1926 TO 1980]',
'collection:graduatetheologicalunion AND (qumran OR targum OR talmud OR mishnah OR philo OR josephus)',
'collection:graduatetheologicalunion AND (ugarit OR akkadian OR assyrian OR babylonian OR archaeology)',
'collection:graduatetheologicalunion AND (isaiah OR jeremiah OR ezekiel OR daniel OR psalms OR job) AND year:[1750 TO 1910]',
'collection:graduatetheologicalunion AND (isaiah OR jeremiah OR ezekiel OR daniel OR psalms OR job) AND year:[1911 TO 1970]',
'collection:graduatetheologicalunion AND (matthew OR mark OR luke OR john OR acts OR romans OR revelation) AND year:[1750 TO 1910]',
'collection:graduatetheologicalunion AND (matthew OR mark OR luke OR john OR acts OR romans OR revelation) AND year:[1911 TO 1970]',
'collection:graduatetheologicalunion AND (calvin OR luther OR origen OR augustine OR chrysostom OR jerome)',
'collection:graduatetheologicalunion AND (lexicon OR concordance OR grammar OR bibliography)'
]
def s(qp):
 q,p=qp
 try:
  r=requests.get(BASE+'/advancedsearch.php',params={'q':q,'fl[]':['identifier','title','creator','date','year','language','subject','volume'],'rows':50,'page':p,'output':'json','sort[]':'date asc'},timeout=10);r.raise_for_status();return r.json().get('response',{}).get('docs',[])
 except:return []
docs={}
with ThreadPoolExecutor(max_workers=20) as ex:
 for f in as_completed([ex.submit(s,(q,p)) for q in qs for p in (1,2)]):
  for d in f.result():
   if d.get('identifier'):docs.setdefault(d['identifier'],d)
def flat(v):return '; '.join(map(str,v)) if isinstance(v,list) else ('' if v is None else str(v))
def meta(d):
 i=d['identifier']
 try:
  r=requests.get(BASE+'/metadata/'+urllib.parse.quote(i),timeout=10);r.raise_for_status();m=r.json()
 except:return None
 md=m.get('metadata',{});c=md.get('collection',[]);c=[c] if isinstance(c,str) else c
 if 'graduatetheologicalunion' not in c:return None
 if str(md.get('access-restricted-item','')).lower()=='true' or str(md.get('printdisabled','')).lower()=='true':return None
 ps=[f for f in m.get('files',[]) if f.get('name','').lower().endswith('.pdf') and 'encrypted' not in f.get('name','').lower() and not f.get('name','').lower().endswith('.lcpdf') and str(f.get('private','false')).lower()!='true']
 if not ps:return None
 p=sorted(ps,key=lambda f:(0 if f.get('source')=='original' else 1,len(f.get('name',''))))[0]
 ic=md.get('imagecount');pages=str(ic) if str(ic).isdigit() else ''
 return {'identifier':i,'title':flat(md.get('title') or d.get('title')),'creator':flat(md.get('creator') or d.get('creator')),'date':flat(md.get('date') or md.get('year') or d.get('date') or d.get('year')),'volume':flat(md.get('volume') or ''),'edition':flat(md.get('edition') or ''),'series':flat(md.get('series') or ''),'language':flat(md.get('language') or d.get('language') or ''),'subject':flat(md.get('subject') or d.get('subject') or ''),'contributor':flat(md.get('contributor') or ''),'mediatype':flat(md.get('mediatype') or ''),'pages':pages,'item_link':BASE+'/details/'+i,'pdf_link':BASE+'/download/'+i+'/'+urllib.parse.quote(p['name'])}
out=[]
with ThreadPoolExecutor(max_workers=24) as ex:
 for f in as_completed([ex.submit(meta,d) for d in list(docs.values())[:180]]):
  x=f.result()
  if x:out.append(x)
out.sort(key=lambda x:(x['date'],x['title']))
json.dump({'unique_discovered':len(docs),'metadata_examined':min(180,len(docs)),'verified_count':len(out),'items':out},open('gtu_fast.json','w'),ensure_ascii=False,indent=2)
print(json.dumps({'unique_discovered':len(docs),'metadata_examined':min(180,len(docs)),'verified_count':len(out)}))