import requests, json, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
BASE='https://archive.org'
queries=[
'hebrew OR "old testament"','aramaic OR targum OR talmud OR mishnah','syriac OR peshitta',
'"new testament" OR gospel OR epistle','septuagint OR "greek bible"','"textual criticism" OR manuscript OR codex',
'papyrus OR papyri OR palaeography','qumran OR "dead sea" OR pseudepigrapha OR apocrypha',
'philo OR josephus OR "second temple"','ugarit OR akkadian OR assyrian OR babylonian OR sumerian',
'"biblical archaeology" OR palestine OR "holy land"','commentary OR commentaries OR exegesis',
'calvin OR luther OR reformation','patristic OR origen OR augustine OR chrysostom OR jerome',
'lexicon OR concordance OR grammar OR bibliography','"journal of biblical" OR "expository times" OR "new testament studies"',
'theology OR doctrine OR creed OR confession','mission OR missionary OR missiology','"church history" OR ecclesiastical',
'judaism OR rabbinic','coptic OR ethiopic OR armenian','isaiah OR jeremiah OR ezekiel OR daniel OR psalms OR job',
'genesis OR pentateuch OR deuteronomy','matthew OR mark OR luke OR john OR acts OR romans OR revelation',
'semitic OR epigraphy OR inscription']
docs={}
for q0 in queries:
    q=f'collection:graduatetheologicalunion AND ({q0})'
    for page in range(1,5):
        params={'q':q,'fl[]':['identifier','title','creator','date','year','language','subject','volume'],'rows':50,'page':page,'output':'json','sort[]':'identifier asc'}
        try:
            r=requests.get(BASE+'/advancedsearch.php',params=params,timeout=30); r.raise_for_status(); js=r.json()
        except Exception:
            continue
        batch=js.get('response',{}).get('docs',[])
        for d in batch:
            ident=d.get('identifier')
            if ident: docs.setdefault(ident,d)
        if len(batch)<50: break
A_terms=['bible','biblical','old testament','new testament','hebrew','aramaic','syriac','semitic','greek','septuagint','textual','manuscript','codex','papyr','qumran','dead sea','apocry','pseudep','talmud','mishnah','targum','philo','josephus','ugarit','akkad','assyri','babylon','sumer','archaeolog','commentar','exeget','lexicon','concordance','grammar','psalm','isaiah','jeremiah','ezekiel','daniel','job','genesis','pentateuch','deuteronomy','gospel','epistle','acts','romans','revelation','christology']
B_terms=['patrist','church history','reformation','theolog','doctrine','creed','confession','apolog','mission','judaism','early christian','liturgy']
def score_doc(d):
    s=' '.join(str(d.get(k,'')) for k in ('title','subject','creator')).lower()
    return sum(3 for t in A_terms if t in s)+sum(1 for t in B_terms if t in s)
ordered=sorted(docs.values(),key=score_doc,reverse=True)[:360]
def flat(v):
    if isinstance(v,list): return '; '.join(str(x) for x in v)
    return '' if v is None else str(v)
def one(d):
    ident=d['identifier']
    try: m=requests.get(BASE+'/metadata/'+urllib.parse.quote(ident),timeout=30).json()
    except Exception: return None
    md=m.get('metadata',{}); coll=md.get('collection',[])
    if isinstance(coll,str): coll=[coll]
    if 'graduatetheologicalunion' not in coll: return None
    if str(md.get('access-restricted-item','')).lower()=='true' or str(md.get('printdisabled','')).lower()=='true': return None
    pdfs=[]
    for f in m.get('files',[]):
        n=f.get('name',''); ln=n.lower()
        if not ln.endswith('.pdf') or ln.endswith('.lcpdf') or 'encrypted' in ln: continue
        if str(f.get('private','false')).lower()=='true': continue
        pdfs.append(f)
    if not pdfs: return None
    pdf=sorted(pdfs,key=lambda f:(0 if f.get('source')=='original' else 1,len(f.get('name',''))))[0]
    title=flat(md.get('title') or d.get('title')); creator=flat(md.get('creator') or d.get('creator'))
    date=flat(md.get('date') or md.get('year') or d.get('date') or d.get('year'))
    volume=flat(md.get('volume') or ''); edition=flat(md.get('edition') or ''); series=flat(md.get('series') or '')
    language=flat(md.get('language') or d.get('language') or ''); subject=flat(md.get('subject') or d.get('subject') or '')
    contributor=flat(md.get('contributor') or ''); mediatype=flat(md.get('mediatype') or '')
    pages=''; ic=md.get('imagecount'); pages=str(ic) if str(ic).isdigit() else ''
    combined=(title+' '+subject+' '+creator).lower(); score=sum(3 for t in A_terms if t in combined)+sum(1 for t in B_terms if t in combined)
    return {'identifier':ident,'title':title,'creator':creator,'date':date,'volume':volume,'edition':edition,'series':series,'language':language,'subject':subject,'contributor':contributor,'mediatype':mediatype,'pages':pages,'item_link':BASE+'/details/'+ident,'pdf_link':BASE+'/download/'+ident+'/'+urllib.parse.quote(pdf['name']),'score':score,'pdf_name':pdf['name']}
verified=[]
with ThreadPoolExecutor(max_workers=12) as ex:
    futs=[ex.submit(one,d) for d in ordered]
    for fut in as_completed(futs):
        x=fut.result()
        if x: verified.append(x)
verified.sort(key=lambda x:(-x['score'],x['title'].lower(),x['date']))
with open('gtu_verified.json','w',encoding='utf-8') as f:
    json.dump({'unique_discovered':len(docs),'metadata_examined':len(ordered),'verified_count':len(verified),'items':verified[:200]},f,ensure_ascii=False,indent=2)
print(json.dumps({'unique_discovered':len(docs),'metadata_examined':len(ordered),'verified_count':len(verified),'saved':min(200,len(verified))}))