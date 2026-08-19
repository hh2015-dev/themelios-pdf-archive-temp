import io, json, re, requests
import fitz
from bs4 import BeautifulSoup

UA='Mozilla/5.0 BSUK-EQ-AnomalyProbe/1.0'
s=requests.Session(); s.headers['User-Agent']=UA

collisions={
'https://biblicalstudies.gospelstudies.org.uk/pdf/eq/1935-4_337.pdf':['Religion and Comparative Religion','Tests in the Final Judgment'],
'https://biblicalstudies.gospelstudies.org.uk/pdf/eq/1939-1_030.pdf':['The Message of Friedrich Nietzsche','Redemption as History and Revelation'],
'https://biblicalstudies.gospelstudies.org.uk/pdf/eq/1951-1_051.pdf':["John Newton's Church History",'The Person and Work of Christ'],
'https://biblicalstudies.gospelstudies.org.uk/pdf/eq/1968-2_110.pdf':['Observations on the Greek Use of the Names and Titles of God in Genesis','An Ecumenical Calvinist'],
'https://biblicalstudies.gospelstudies.org.uk/pdf/eq/1980-3_130.pdf':['Exodus Motifs in First Samuel 7 and 8','The Eighteenth Century Methodist Revival Reconsidered'],
'https://biblicalstudies.gospelstudies.org.uk/pdf/eq/1991-4_305.pdf':['The Message of the Book of Job','Melchizedek'],
}

broken_candidates={
'1952-2_justifation_hughes.pdf':['1952-2_078.pdf','1952-2_justification_hughes.pdf','1952-2_justification_hughes.pdf'],
'1958-4_morris.pdf':['1958-4_196.pdf'],
'1959-3_143n.pdf':['1959-3_143.pdf'],
'1971-1_131.pdf':['1971-3_131.pdf'],
'1991-2_clifford.pdf':['1991-2_099.pdf'],
'1991-2_parker.pdf':['1991-2_123.pdf'],
'1995-3_clifford.pdf':['1995-3_211.pdf'],
'1995-4_335bk.pdf':['1995-4_335.pdf'],
'2003_bombshell_stewart.pdf':['2003-3_215.pdf'],
}
BASE='https://biblicalstudies.gospelstudies.org.uk/pdf/eq/'

def fetch_pdf(url):
    r=s.get(url,timeout=45); status=r.status_code; ct=r.headers.get('content-type',''); data=r.content
    ok=status==200 and data.startswith(b'%PDF-')
    text=''; pages=None
    if ok:
        try:
            d=fitz.open(stream=data,filetype='pdf'); pages=d.page_count
            text=' '.join(d[p].get_text('text') for p in range(min(3,d.page_count)))
            text=re.sub(r'\s+',' ',text).strip()[:5000]
        except Exception as e: text='OPEN_ERROR '+repr(e)
    return {'url':url,'status':status,'content_type':ct,'size':len(data),'ok_pdf':ok,'pages':pages,'text':text}

out={'collisions':[],'broken_candidates':[]}
for url,titles in collisions.items():
    x=fetch_pdf(url)
    low=x['text'].lower()
    matches=[t for t in titles if re.sub(r'[^a-z0-9]+',' ',t.lower()).strip()[:25] in re.sub(r'[^a-z0-9]+',' ',low)]
    x['expected_titles']=titles; x['title_matches']=matches
    out['collisions'].append(x)
    print('COLLISION',json.dumps(x,ensure_ascii=False),flush=True)

for old,cands in broken_candidates.items():
    rec={'broken_name':old,'candidates':[]}
    for c in cands:
        x=fetch_pdf(BASE+c); rec['candidates'].append(x)
        print('RECOVERY',old,json.dumps(x,ensure_ascii=False),flush=True)
    out['broken_candidates'].append(rec)
open('eq_anomaly_probe.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
