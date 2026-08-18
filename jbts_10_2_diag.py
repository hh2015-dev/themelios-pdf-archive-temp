import re,html,requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin,unquote
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 BSUK-JBTS-Diag/1.0'})
issues='https://jbtsonline.org/issues/'
r=S.get(issues,timeout=30); print('ISSUES',r.status_code,r.url,len(r.text))
s=BeautifulSoup(r.text,'html.parser')
# isolate section 10.2
h=None
for x in s.find_all(['h2','h3']):
    t=' '.join(x.stripped_strings)
    if re.search(r'JBTS\s+Volume\s+10\s*\|\s*Issue\s*2',t,re.I): h=x; break
if not h: raise SystemExit('10.2 heading not found')
pages=[]
for el in h.find_all_next():
    if el is not h and el.name in ('h2','h3') and re.match(r'^JBTS Volume', ' '.join(el.stripped_strings), re.I): break
    if el.name=='a' and el.get('href'):
        t=' '.join(el.stripped_strings).strip(); u=urljoin(issues,el['href'])
        if t and '/2025/' in u and u not in [x[0] for x in pages]: pages.append((u,t))
print('ARTICLE_PAGES',len(pages))
for i,(u,title) in enumerate(pages,1):
    rr=S.get(u,timeout=30,allow_redirects=True)
    raw=rr.text
    print('\n###',i,title,'\nURL',rr.url,'STATUS',rr.status_code,'LEN',len(raw))
    soup=BeautifulSoup(raw,'html.parser')
    candidates=[]
    # all attributes
    for tag in soup.find_all(True):
        for k,v in tag.attrs.items():
            vals=v if isinstance(v,list) else [v]
            for vv in vals:
                if not isinstance(vv,str): continue
                dv=html.unescape(vv).replace('\\/','/')
                if '.pdf' in dv.lower() or 'pdf' in k.lower() or 'download' in k.lower():
                    candidates.append((tag.name,k,dv))
    # regex raw html around pdf occurrences
    decoded=html.unescape(raw).replace('\\/','/')
    for m in re.finditer(r'(?i).{0,180}pdf.{0,220}',decoded,re.S):
        snippet=re.sub(r'\s+',' ',m.group(0))
        print('PDF_SNIP',snippet[:500])
    for c in candidates[:100]: print('ATTR',c)
    # Extract absolute/relative pdf URLs from text/attrs/query params
    found=[]
    patterns=[r'https?://[^\s"\'<>]+?\.pdf(?:\?[^\s"\'<>]*)?', r'(?<!:)//[^\s"\'<>]+?\.pdf(?:\?[^\s"\'<>]*)?', r'["\']([^"\']+?\.pdf(?:\?[^"\']*)?)["\']']
    for pat in patterns:
        for m in re.finditer(pat,decoded,re.I):
            val=m.group(1) if m.lastindex else m.group(0)
            val=unquote(val)
            if val.startswith('//'): val='https:'+val
            val=urljoin(rr.url,val)
            if val not in found:found.append(val)
    print('FOUND_PDF_URLS',len(found))
    for x in found: print('PDFURL',x)
