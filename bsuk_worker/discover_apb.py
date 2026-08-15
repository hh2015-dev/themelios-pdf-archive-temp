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
for page in PAGES:
    r=requests.get(page,headers=headers,timeout=60)
    print('PAGE',page,r.status_code,len(r.content))
    r.raise_for_status()
    soup=BeautifulSoup(r.text,'html.parser')
    for a in soup.find_all('a', href=True):
        href=a['href']
        if '.pdf' not in href.lower():
            continue
        url=urljoin(page,href)
        text=' '.join(a.stripped_strings)
        parent=a.parent
        context=' '.join(parent.stripped_strings) if parent else text
        context=re.sub(r'\s+',' ',context).strip()
        rows.append((page,url,text,context))
# de-duplicate by URL
seen=set(); out=[]
for row in rows:
    if row[1] in seen: continue
    seen.add(row[1]); out.append(row)
with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f); w.writerow(['page','pdf_url','anchor_text','context']); w.writerows(out)
print('PDF_LINKS',len(out))
for row in out[:20]: print(row[1], '||', row[3][:180])
