import os, re, time, tempfile
from pathlib import Path
import requests, fitz

IDENT='ashlandtheologic71121alde'
URL=f'https://archive.org/download/{IDENT}/{IDENT}.pdf'
OUT=Path('ashland_vol11_check'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers['User-Agent']='BSUK-Ashland-Vol11-Check/1.0'

def download(dest):
    last=None
    for k in range(8):
        try:
            with S.get(URL,stream=True,timeout=(30,180),allow_redirects=True) as r:
                r.raise_for_status()
                with open(dest,'wb') as f:
                    for b in r.iter_content(1024*1024):
                        if b:f.write(b)
            return
        except Exception as e:
            last=e; time.sleep(min(20,2+k*2))
    raise RuntimeError(last)

def norm(t): return re.sub(r'\s+',' ',t.replace('\x00',' ')).strip()

with tempfile.TemporaryDirectory() as td:
    pdf=Path(td)/'src.pdf'; download(pdf)
    doc=fitz.open(pdf)
    lines=[]
    # Inspect PDF pages 251-315 (1-based): the region previously attributed to vol.10 before vol.12 starts.
    for p1 in range(251,316):
        page=doc.load_page(p1-1)
        text=norm(page.get_text('text'))
        flags=[]
        up=text.upper()
        for token in ['1977','1978','1979','VOLUME XI','VOL. XI','VOLUME 11','VOL. 11','ASHLAND THEOLOGICAL BULLETIN','CONTENTS','SPRING','FALL']:
            if token in up: flags.append(token)
        if flags or p1 in range(270,316):
            lines.append(f'\n===== PDF PAGE {p1} FLAGS={flags} =====\n{text[:4000]}\n')
    (OUT/'pages_251_315_text.txt').write_text('\n'.join(lines),encoding='utf-8')
    # Render pages 270-315 at modest resolution for visual inspection.
    for p1 in range(270,316):
        page=doc.load_page(p1-1)
        pix=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2),alpha=False)
        pix.save(OUT/f'page_{p1:03d}.jpg')
    doc.close()
print('DONE', flush=True)
