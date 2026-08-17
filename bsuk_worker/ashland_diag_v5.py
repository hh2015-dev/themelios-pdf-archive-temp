import json,re,time,tempfile,os
from pathlib import Path
import requests,fitz
S=requests.Session();S.headers['User-Agent']='BSUK-Ashland-Diag/5.0'

def get(url,stream=False):
    last=None
    for k in range(10):
        try:
            r=S.get(url,stream=stream,timeout=(30,180),allow_redirects=True)
            if r.status_code in (200,206): return r
            last=f'{r.status_code} {r.url}'; r.close()
        except Exception as e:last=repr(e)
        time.sleep(min(30,2+k*2))
    raise RuntimeError(f'GET failed {url}: {last}')

def meta(ident):
    r=get(f'https://archive.org/metadata/{ident}');d=r.json();r.close();return d

def print_files(ident):
    d=meta(ident)
    print(f'META|{ident}|server={d.get("d1")}|server2={d.get("d2")}|dir={d.get("dir")}',flush=True)
    for f in d.get('files',[]):
        n=f.get('name','');fmt=str(f.get('format',''));size=f.get('size');priv=f.get('private');src=f.get('source')
        if any(x in n.lower() for x in ['pdf','jp2','djvu','text','torrent','scandata','abbyy']) or any(x in fmt.lower() for x in ['pdf','jp2','djvu','text','torrent']):
            print('FILE|'+json.dumps({'name':n,'format':fmt,'size':size,'private':priv,'source':src},ensure_ascii=False),flush=True)

def download_to(url,p):
    r=get(url,stream=True)
    print(f'DOWNLOAD_URL|{r.url}|status={r.status_code}|len={r.headers.get("Content-Length")}',flush=True)
    with open(p,'wb') as f:
        for b in r.iter_content(1024*1024):
            if b:f.write(b)
    r.close()

def norm(t):return re.sub(r'\s+',' ',t.upper().replace('–','-').replace('—','-'))

def inspect_7_12():
    ident='ashlandtheologic71121alde';u=f'https://archive.org/download/{ident}/{ident}.pdf'
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'x.pdf';download_to(u,p);print(f'PDF_SIZE|{p.stat().st_size}',flush=True)
        d=fitz.open(p)
        for i in range(d.page_count):
            t=norm(d.load_page(i).get_text('text'))
            # print title/contents/year transition candidates around volumes 10/11
            if (239<=i<=329 and any(x in t for x in ['ASHLAND','THEOLOGICAL','1977','1978','VOLUME','CONTENTS'])) or ('CONTENTS' in t and 'ASHLAND' in t):
                print(f'PAGE|{i+1}|{t[:1300]}',flush=True)
        d.close()

def main():
    print_files('ashlandtheologic1161alde')
    print_files('ashlandtheologic3136bake')
    inspect_7_12()
if __name__=='__main__':main()
