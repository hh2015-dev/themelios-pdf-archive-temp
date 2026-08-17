import re, requests, fitz, tempfile
from pathlib import Path
S=requests.Session();S.headers['User-Agent']='BSUK-Ashland-Diag/4.0'

def norm(t):return re.sub(r'\s+',' ',t.upper())

def probe(ident):
 u=f'https://archive.org/download/{ident}/{ident}.pdf'
 try:
  r=S.get(u,headers={'Range':'bytes=0-1023'},stream=True,timeout=(20,60),allow_redirects=True)
  print(f'PROBE|{ident}|status={r.status_code}|content_range={r.headers.get("Content-Range")}|content_length={r.headers.get("Content-Length")}|final={r.url}',flush=True)
  r.close()
 except Exception as e:print(f'PROBE_ERROR|{ident}|{repr(e)}',flush=True)

def main():
 for i in ['ashlandtheologic1161alde','ashlandtheologic19124with','ashlandtheologic3136bake']:
  probe(i)
 ident='ashlandtheologic71121alde';u=f'https://archive.org/download/{ident}/{ident}.pdf'
 with tempfile.TemporaryDirectory() as td:
  p=Path(td)/'x.pdf'
  with S.get(u,stream=True,timeout=(20,120)) as r:
   r.raise_for_status()
   with open(p,'wb') as f:
    for b in r.iter_content(1024*1024):
     if b:f.write(b)
  d=fitz.open(p)
  for i in range(d.page_count):
   t=norm(d.load_page(i).get_text('text'))
   if 'CONTENTS' in t and ('ASHLAND' in t or 'THEOLOGICAL' in t):
    print(f'CONTENTS_PAGE|{i+1}|{t[:700]}',flush=True)
  print('---TRANSITION_240_330---',flush=True)
  for i in range(239,min(330,d.page_count)):
   t=norm(d.load_page(i).get_text('text'))
   if any(x in t for x in ['ASHLAND','THEOLOGICAL','1977','1978','VOLUME','VOL.','CONTENTS']):
    print(f'PAGE|{i+1}|{t[:900]}',flush=True)
  d.close()
if __name__=='__main__':main()
