from pathlib import Path
import hashlib, csv, requests

MIRROR='https://biblicalstudies.gospelstudies.org.uk/pdf/abtapl'
PRIMARY='https://www.biblicalstudies.org.uk/pdf/abtapl'
OUT=Path('bsuk_output/abtapl')
OUT.mkdir(parents=True, exist_ok=True)
headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36','Accept':'application/pdf,*/*;q=0.8'}
plan={
  2:[*[f'{i:02d}' for i in range(1,15)],'15_16','17','18'],
  3:[f'{i:02d}' for i in range(1,10)],
  4:['01','02','03'],5:['01','02','03'],6:['01','02','03'],7:['01','02','03'],8:['01','02','03'],9:['01','02','03'],
}
rows=[]
for volume, parts in plan.items():
  vd=OUT/f'volume-{volume:03d}'
  vd.mkdir(parents=True,exist_ok=True)
  for part in parts:
    fn=f'{volume:02d}-{part}.pdf'
    dest=vd/fn
    ok=False; err=''
    for base in (MIRROR,PRIMARY):
      url=f'{base}/{fn}'
      try:
        with requests.get(url,headers=headers,stream=True,timeout=120,allow_redirects=True) as r:
          print('GET',url,'->',r.status_code,r.headers.get('content-type'),r.url,flush=True)
          r.raise_for_status(); h=hashlib.sha256(); size=0
          with dest.open('wb') as f:
            for chunk in r.iter_content(1024*256):
              if chunk: f.write(chunk); h.update(chunk); size+=len(chunk)
        sig=dest.read_bytes()[:5]
        if sig!=b'%PDF-': raise RuntimeError(f'not PDF: {sig!r}')
        rows.append([volume,part,fn,url,r.url,size,h.hexdigest(),'OK'])
        print('OK',fn,size,h.hexdigest(),flush=True); ok=True; break
      except Exception as e:
        err=repr(e); print('FAILED',url,err,flush=True)
        if dest.exists(): dest.unlink()
    if not ok:
      rows.append([volume,part,fn,'','',0,'',f'FAILED {err}'])
with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.writer(f); w.writerow(['volume','issue_part','filename','source_url','final_url','bytes','sha256','status']); w.writerows(rows)
failed=[r for r in rows if r[-1]!='OK']
print('SUMMARY total=',len(rows),'ok=',len(rows)-len(failed),'failed=',len(failed),flush=True)
if failed: raise SystemExit(2)
