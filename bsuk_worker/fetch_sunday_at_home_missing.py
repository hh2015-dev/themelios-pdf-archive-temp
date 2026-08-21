from pathlib import Path
import hashlib, requests, json
url='https://biblicalstudies.org.uk/pdf/sunday-at-home/1889/1889_449.pdf'
out=Path('sunday_at_home_missing'); out.mkdir(exist_ok=True)
r=requests.get(url,timeout=60,headers={'User-Agent':'Mozilla/5.0 BSUK archival fetch'})
r.raise_for_status()
data=r.content
assert data.startswith(b'%PDF-'), 'not a PDF'
fn=out/'1889_449.pdf'; fn.write_bytes(data)
meta={'url':url,'file':fn.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
(out/'meta.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
print(json.dumps(meta,indent=2))
