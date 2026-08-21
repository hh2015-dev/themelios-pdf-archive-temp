from pathlib import Path
import requests, hashlib, json, sys

OUT=Path('sword_and_trowel_archive'); OUT.mkdir(exist_ok=True)
BASES=[
 'https://biblicalstudies.gospelstudies.org.uk/pdf/sword-and-the-trowel/sword-and-the-trowel_{year}.pdf',
 'https://www.gospelstudies.org.uk/biblicalstudies/pdf/sword-and-the-trowel/sword-and-the-trowel_{year}.pdf',
 'https://www.biblicalstudies.org.uk/pdf/sword-and-the-trowel/sword-and-the-trowel_{year}.pdf',
]
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 BSUK archival validator'
manifest=[]; errors=[]
for vol,year in enumerate(range(1865,1905),1):
    data=None; used=None
    for tpl in BASES:
        u=tpl.format(year=year)
        try:
            r=S.get(u,timeout=120)
            if r.status_code==200 and r.content.startswith(b'%PDF-') and len(r.content)>10000:
                data=r.content; used=u; break
        except Exception:
            pass
    if data is None:
        errors.append({'volume':vol,'year':year}); continue
    batch=((vol-1)//10)+1
    folder=OUT/f'batch_{batch}'/f'Volume {vol:03d}'
    folder.mkdir(parents=True,exist_ok=True)
    name=f'The Sword and the Trowel - Volume {vol:03d} ({year}) - Complete Volume.pdf'
    p=folder/name; p.write_bytes(data)
    manifest.append({'volume':vol,'year':year,'file':str(p.relative_to(OUT)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'url':used})
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(OUT/'errors.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
print(json.dumps({'downloaded':len(manifest),'errors':len(errors),'total_bytes':sum(x['bytes'] for x in manifest)},indent=2))
if errors: sys.exit(2)
