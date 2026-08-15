from bs4 import BeautifulSoup
from urllib.parse import urljoin
import csv, re, requests
from pathlib import Path

PAGES = [
    'https://www.biblicalstudies.org.uk/articles_apb_01.php',
    'https://www.biblicalstudies.org.uk/articles_apb_02.php',
]
OUT = Path('apb_discovery')
OUT.mkdir(exist_ok=True)
headers={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36'}
rows=[]
debug=[]
for page in PAGES:
    r=requests.get(page,headers=headers,timeout=60)
    print('PAGE',page,r.status_code,len(r.content),r.url)
    r.raise_for_status()
    html=r.text
    soup=BeautifulSoup(html,'html.parser')
    debug.append(f'PAGE {page}\n')
    # Preserve representative raw HTML around a known article for diagnosis.
    for needle in ['Iconic leadership','A Pauline letter and a pagan prophet']:
        i=html.find(needle)
        if i >= 0:
            debug.append(html[max(0,i-1200):i+1800]+'\n---\n')
    # Candidate links: direct PDFs, /pdf/ paths, links inside rows containing APB citations,
    # and links whose attributes mention pdf/download/article.
    for a in soup.find_all('a', href=True):
        href=a.get('href','').strip()
        url=urljoin(page,href)
        text=' '.join(a.stripped_strings)
        parent=a.find_parent(['tr','li','p','div','td'])
        context=' '.join(parent.stripped_strings) if parent else text
        context=re.sub(r'\s+',' ',context).strip()
        attrs=' '.join(f'{k}={v}' for k,v in a.attrs.items())
        key=' '.join([href,text,context,attrs]).lower()
        if ('.pdf' in key or '/pdf/' in key or 'download' in key or
            ('acta patristica et byzantina' in context.lower() and href not in ['#',''])):
            rows.append((page,url,href,text,context,attrs))
    # Also inspect non-anchor attributes that may encode PDF/download URLs.
    for tag in soup.find_all(True):
        attrs=tag.attrs or {}
        for k,v in attrs.items():
            val=' '.join(v) if isinstance(v,list) else str(v)
            low=val.lower()
            if '.pdf' in low or '/pdf/' in low:
                debug.append(f'TAG {tag.name} {k}={val}\n')
# de-duplicate by resolved URL + context
seen=set(); out=[]
for row in rows:
    sig=(row[1],row[4])
    if sig in seen: continue
    seen.add(sig); out.append(row)
with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f); w.writerow(['page','resolved_url','raw_href','anchor_text','context','attrs']); w.writerows(out)
(OUT/'debug.txt').write_text('\n'.join(debug),encoding='utf-8')
print('CANDIDATES',len(out))
for row in out[:40]: print(row[1], '||', row[4][:180])
