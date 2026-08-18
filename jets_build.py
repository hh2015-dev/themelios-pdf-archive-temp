import os, sys, json, time, hashlib, urllib.request, urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from pypdf import PdfReader, PdfWriter
except Exception:
    print('pypdf is required', file=sys.stderr); raise

START=int(os.environ.get('START_VOL','1'))
END=int(os.environ.get('END_VOL','64'))
OUT=Path(os.environ.get('OUT_DIR',f'out_{START:02d}_{END:02d}'))
OUT.mkdir(parents=True,exist_ok=True)
UA='Mozilla/5.0 JETS-archive-builder/1.0'
manifest=json.load(open('jets_manifest.json',encoding='utf-8'))
issues=[i for i in manifest['issues'] if START <= i['volume'] <= END]


def fetch_pdf(item, dest):
    last=''
    for attempt in range(4):
        try:
            req=urllib.request.Request(item['url'],headers={'User-Agent':UA,'Accept':'application/pdf,*/*;q=0.8'})
            with urllib.request.urlopen(req,timeout=60) as r:
                data=r.read()
            if not data.startswith(b'%PDF'):
                raise ValueError(f'not PDF ({data[:30]!r})')
            dest.write_bytes(data)
            # parse validation
            reader=PdfReader(str(dest),strict=False)
            if len(reader.pages)<1: raise ValueError('zero-page PDF')
            return {'ok':True,'bytes':len(data),'pages':len(reader.pages),'sha256':hashlib.sha256(data).hexdigest()}
        except Exception as e:
            last=repr(e); time.sleep(1.5*(attempt+1))
    return {'ok':False,'error':last}

results=[]; failed=[]
for idx, issue in enumerate(issues,1):
    series=issue['series']; vol=issue['volume']; no=issue['issue']; year=issue.get('year')
    work=OUT/f'_work_{vol:03d}_{no:02d}'; work.mkdir(exist_ok=True)
    jobs=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for j,item in enumerate(issue['pdfs'],1):
            dest=work/f'{j:03d}.pdf'
            jobs.append((j,item,dest,ex.submit(fetch_pdf,item,dest)))
        dl=[]
        for j,item,dest,fut in jobs:
            r=fut.result(); r.update({'index':j,'url':item['url'],'citation':item['citation'],'path':str(dest)})
            dl.append(r)
    bad=[d for d in dl if not d['ok']]
    if bad:
        failed.append({'volume':vol,'issue':no,'year':year,'failed':bad,'expected':len(dl)})
        print(f'FAIL {vol}.{no}: {len(bad)}/{len(dl)} downloads failed')
        continue
    title=('Bulletin of the Evangelical Theological Society' if series=='BETS' else 'Journal of the Evangelical Theological Society')
    fname=f'{title} - Volume {vol:03d} Issue {no:02d}' + (f' - {year}' if year else '') + ' - Reconstructed from official article PDFs.pdf'
    out=OUT/fname
    writer=PdfWriter(); pages=0
    try:
        for d in sorted(dl,key=lambda x:x['index']):
            rd=PdfReader(d['path'],strict=False)
            for p in rd.pages: writer.add_page(p); pages+=1
        with out.open('wb') as f: writer.write(f)
        # validate merged output
        chk=PdfReader(str(out),strict=False)
        if len(chk.pages)!=pages: raise ValueError(f'merged page count mismatch {len(chk.pages)} != {pages}')
        data=out.read_bytes()
        results.append({'series':series,'volume':vol,'issue':no,'year':year,'file':fname,'source_pdf_count':len(dl),'pages':pages,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        print(f'OK {idx}/{len(issues)} {vol}.{no}: {len(dl)} PDFs -> {pages} pages -> {len(data)} bytes')
    except Exception as e:
        failed.append({'volume':vol,'issue':no,'year':year,'merge_error':repr(e),'expected':len(dl)})
        print(f'FAIL MERGE {vol}.{no}: {e!r}')
    finally:
        for p in work.glob('*'): p.unlink(missing_ok=True)
        work.rmdir()

report={'start_volume':START,'end_volume':END,'issues_expected':len(issues),'issues_built':len(results),'issues_failed':len(failed),'results':results,'failed':failed}
with open(OUT/'build_report.json','w',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k not in ('results','failed')},indent=2))
if failed: sys.exit(2)
