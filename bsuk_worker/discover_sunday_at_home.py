import json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

OUT=Path('sunday_at_home_discovery'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers['User-Agent']='Mozilla/5.0 BSUK archival discovery'
BASES=['https://biblicalstudies.org.uk/','https://www.biblicalstudies.org.uk/','https://biblicalstudies.gospelstudies.org.uk/','https://www.gospelstudies.org.uk/biblicalstudies/']

def fetch_rel(rel):
    errs=[]
    for base in BASES:
        u=urljoin(base,rel)
        try:
            r=S.get(u,timeout=30,allow_redirects=True)
            if r.status_code==200 and len(r.text)>1000:
                return r,u
            errs.append(f'{u} {r.status_code} {len(r.content)}')
        except Exception as e: errs.append(f'{u} {e!r}')
    return None, errs

pages=[]
for i in range(1,21):
    rel=f'articles_sunday-at-home_{i:02d}.php'
    r,src=fetch_rel(rel)
    if r is None:
        pages.append({'page':i,'rel':rel,'ok':False,'errors':src})
        continue
    html=r.text
    (OUT/f'page_{i:02d}.html').write_text(html,encoding='utf-8')
    soup=BeautifulSoup(html,'html.parser')
    title=(soup.title.get_text(' ',strip=True) if soup.title else '')
    headings=[h.get_text(' ',strip=True) for h in soup.find_all(['h1','h2','h3','h4'])]
    years=[]
    for tag in soup.find_all(id=True):
        m=re.fullmatch(r'y(\d{4})',str(tag.get('id')))
        if m: years.append(int(m.group(1)))
    # also detect year headings
    for h in headings:
        for y in re.findall(r'(?<!\d)(18\d{2}|19\d{2}|20\d{2})(?!\d)',h): years.append(int(y))
    pdfs=[]; nav=[]
    for a in soup.find_all('a',href=True):
        href=a['href'].strip(); text=a.get_text(' ',strip=True)
        absu=urljoin(src,href)
        if re.search(r'articles_sunday-at-home_\d+\.php',href,re.I): nav.append({'text':text,'href':href,'url':absu})
        if '.pdf' in href.lower():
            pdfs.append({'text':text,'href':href,'url':absu})
    pages.append({'page':i,'rel':rel,'ok':True,'source':src,'title':title,'headings':headings,'years':sorted(set(years)),'pdfs':pdfs,'nav':nav})
    time.sleep(.2)

# unique exact linked PDFs
allpdf=[]; seen=set()
for p in pages:
    if not p.get('ok'): continue
    for x in p['pdfs']:
        key=x['url'].split('#')[0]
        if key not in seen:
            seen.add(key); allpdf.append({'page':p['page'],**x})

summary={
 'pages_ok':[p['page'] for p in pages if p.get('ok')],
 'pages_missing':[p['page'] for p in pages if not p.get('ok')],
 'years':sorted(set(y for p in pages if p.get('ok') for y in p.get('years',[]))),
 'unique_pdf_count':len(allpdf),
 'page_pdf_counts':{str(p['page']):len(p.get('pdfs',[])) for p in pages if p.get('ok')},
}
(OUT/'pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'pdf_links.json').write_text(json.dumps(allpdf,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
