import json, re, urllib.request, urllib.parse
from html.parser import HTMLParser
from collections import defaultdict, Counter

PAGES = [
    'https://biblicalstudies.gospelstudies.org.uk/articles_bets.php',
    'https://biblicalstudies.gospelstudies.org.uk/articles_bets2.php',
    'https://biblicalstudies.gospelstudies.org.uk/articles_jets-01.php',
    'https://biblicalstudies.gospelstudies.org.uk/articles_jets-02.php',
    'https://biblicalstudies.gospelstudies.org.uk/articles_jets-03.php',
    'https://biblicalstudies.gospelstudies.org.uk/articles_jets-04.php',
    'https://biblicalstudies.gospelstudies.org.uk/articles_jets-05.php',
    'https://biblicalstudies.gospelstudies.org.uk/articles_jets-06.php',
]
UA = 'Mozilla/5.0 JETS-archive-discovery/1.0'

class P(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True); self.base=base; self.a=None; self.links=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=='a':
            d=dict(attrs); self.a={'href':d.get('href',''), 'text':[]}
    def handle_data(self, data):
        if self.a is not None: self.a['text'].append(data)
    def handle_endtag(self, tag):
        if tag.lower()=='a' and self.a is not None:
            href=urllib.parse.urljoin(self.base,self.a['href']); text=' '.join(''.join(self.a['text']).split())
            self.links.append((href,text)); self.a=None

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=45) as r:
        return r.read().decode('utf-8','replace')

rows=[]; page_stats=[]
pat=re.compile(r'(Bulletin of the Evangelical Theological Society|Journal of the Evangelical Theological Society)\s+(\d+)\.(\d+)\s*\(([^)]*)\)', re.I)
for page in PAGES:
    html=get(page); p=P(page); p.feed(html)
    n=0
    for href,text in p.links:
        m=pat.search(text)
        if not m: continue
        # BiblicalStudies marks usable items as pdf in anchor text; hrefs may be local or official.
        if 'pdf' not in text.lower() and '.pdf' not in href.lower(): continue
        series='BETS' if m.group(1).lower().startswith('bulletin') else 'JETS'
        vol=int(m.group(2)); issue=int(m.group(3)); year_m=re.search(r'\b(19|20)\d{2}\b',m.group(4)); year=int(year_m.group()) if year_m else None
        host=urllib.parse.urlparse(href).netloc.lower()
        rows.append({'series':series,'volume':vol,'issue':issue,'year':year,'citation':text,'url':href,'host':host,'source_page':page})
        n+=1
    page_stats.append({'page':page,'links':n,'bytes':len(html)})

# de-dupe same PDF URL within an issue
seen=set(); clean=[]
for r in rows:
    k=(r['volume'],r['issue'],r['url'])
    if k not in seen: seen.add(k); clean.append(r)
rows=clean
issues=defaultdict(list)
for r in rows: issues[(r['series'],r['volume'],r['issue'],r['year'])].append(r)

issue_rows=[]
for (series,vol,issue,year), items in sorted(issues.items(), key=lambda x:(x[0][1],x[0][2])):
    issue_rows.append({'series':series,'volume':vol,'issue':issue,'year':year,'pdf_count':len(items),'hosts':dict(Counter(x['host'] for x in items)),'pdfs':items})

summary={
 'source':'BiblicalStudies.org.uk / Theology on the Web JETS+BETS index pages',
 'pages':page_stats,
 'article_pdf_links':len(rows),
 'issues_with_pdf_links':len(issue_rows),
 'volumes_with_pdf_links':len(set(r['volume'] for r in rows)),
 'volume_min':min((r['volume'] for r in rows),default=None),
 'volume_max':max((r['volume'] for r in rows),default=None),
 'series_counts':dict(Counter(r['series'] for r in rows)),
 'host_counts':dict(Counter(r['host'] for r in rows)),
 'issues_by_volume':{str(v):len(set(r['issue'] for r in rows if r['volume']==v)) for v in sorted(set(r['volume'] for r in rows))},
 'pdfs_by_volume':{str(v):sum(1 for r in rows if r['volume']==v) for v in sorted(set(r['volume'] for r in rows))},
}
with open('jets_manifest.json','w',encoding='utf-8') as f: json.dump({'summary':summary,'issues':issue_rows},f,ensure_ascii=False,indent=2)
with open('jets_summary.txt','w',encoding='utf-8') as f:
    f.write(json.dumps(summary,ensure_ascii=False,indent=2)); f.write('\n\nISSUES\n')
    for i in issue_rows: f.write(f"{i['series']} {i['volume']}.{i['issue']} ({i['year']}): {i['pdf_count']} PDFs {i['hosts']}\n")
print(json.dumps(summary,indent=2))
