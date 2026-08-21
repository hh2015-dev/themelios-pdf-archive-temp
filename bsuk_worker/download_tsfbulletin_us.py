import os, json, hashlib
import requests

BASE='https://biblicalstudies.org.uk/pdf/tsf-bulletin-us/issues/'
OUT='tsf_stage'
TITLE='Theological Students Fellowship Bulletin (US)'
os.makedirs(OUT, exist_ok=True)
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0'})

corpus=[]
early={
  1:(1978,[('Jan.',['jan','january']),('April',['apr','april']),('May',['may']),('October',['oct','october']),('Nov.',['nov','november'])]),
  2:(1979,[('January',['jan','january']),('March',['mar','march']),('May',['may']),('Oct.',['oct','october']),('Nov.',['nov','november'])]),
  3:(1980,[('March',['mar','march']),('April',['apr','april'])])
}
for v,(yr,issues) in early.items():
    for n,(label,slugs) in enumerate(issues,1):
        candidates=[f'{BASE}tsf-news-and-reviews_{yr}-{slug}.pdf' for slug in slugs]
        corpus.append({'volume':v,'issue_number':n,'year':str(yr),'issue_label':label,'candidates':candidates})

start_year={4:1980,5:1981,6:1982,7:1983,8:1984,9:1985,10:1986}
for v,yr in start_year.items():
    for n in range(1,6):
        candidates=[
            f'{BASE}tsf-bulletin_{v:02d}-{n}_{yr}.pdf',
            f'{BASE}tsf-bulletin_{v:02d}-{n}_{yr+1}.pdf'
        ]
        corpus.append({'volume':v,'issue_number':n,'year':f'{yr}/{yr+1}','issue_label':f'{v}.{n}','candidates':candidates})

manifest={'source_page':'https://biblicalstudies.org.uk/articles_tsfbulletin-us.php','title':TITLE,'expected':len(corpus),'issues':[],'errors':[],'independent_indexes':[]}
for x in corpus:
    data=None; used=None; last=None
    for url in x['candidates']:
        try:
            r=s.get(url,timeout=120,allow_redirects=True)
            if r.status_code==200 and r.content.startswith(b'%PDF'):
                data=r.content; used=url; break
            last=f'{r.status_code} {r.headers.get("content-type")} {len(r.content)}'
        except Exception as e:
            last=str(e)
    name=f'{TITLE} - Volume {x["volume"]:03d} Issue {x["issue_number"]:02d}.pdf'
    if data is None:
        manifest['errors'].append({**x,'file':name,'error':last})
        print('ERR',x['volume'],x['issue_number'],last,x['candidates'])
        continue
    path=os.path.join(OUT,name)
    with open(path,'wb') as f: f.write(data)
    rec={**x,'url':used,'file':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'valid_pdf':True}
    rec.pop('candidates',None)
    manifest['issues'].append(rec)
    print('OK',rec['volume'],rec['issue_number'],rec['issue_label'],rec['bytes'],used)

with open(os.path.join(OUT,'manifest.json'),'w',encoding='utf-8') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'manifest.txt'),'w',encoding='utf-8') as f:
    f.write(f"TITLE={TITLE}\nEXPECTED={manifest['expected']}\nISSUES={len(manifest['issues'])}\nERRORS={len(manifest['errors'])}\nINDEX_PDFS=0\n")
    for v in range(1,11):
        ok=sum(1 for z in manifest['issues'] if z['volume']==v)
        f.write(f"VOLUME {v:03d}: {ok} issues\n")
    f.write('\n')
    for z in manifest['issues']:
        f.write(f"V{z['volume']:03d} I{z['issue_number']:02d}\t{z['year']}\t{z['issue_label']}\t{z['bytes']}\t{z['file']}\t{z['url']}\n")
    if manifest['errors']:
        f.write('\nERRORS\n')
        for e in manifest['errors']: f.write(json.dumps(e,ensure_ascii=False)+'\n')
print(json.dumps({'expected':manifest['expected'],'issues':len(manifest['issues']),'errors':len(manifest['errors'])},indent=2))
