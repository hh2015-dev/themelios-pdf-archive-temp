import json, re, requests
import fitz

UA='Mozilla/5.0 BSUK-EQ-AnomalyProbe/1.1'
s=requests.Session(); s.headers['User-Agent']=UA
BASE='https://biblicalstudies.gospelstudies.org.uk/pdf/eq/'

candidates={
'Tests in the Final Judgment, Vol 7.4 pp 351-363':'1935-4_351.pdf',
'The Person and Work of Christ, Vol 23.3 pp 213-218':'1951-3_213.pdf',
'Observations on the Greek Use of the Names and Titles of God in Genesis, Vol 40.2 pp 103-109':'1968-2_103.pdf',
'The Eighteenth Century Methodist Revival Reconsidered, Vol 53.3 pp 130-148':'1981-3_130.pdf',
}

def fetch_pdf(url):
    r=s.get(url,timeout=45); data=r.content
    out={'url':url,'status':r.status_code,'content_type':r.headers.get('content-type',''),'size':len(data),'ok_pdf':r.status_code==200 and data.startswith(b'%PDF-'),'pages':None,'text':''}
    if out['ok_pdf']:
        d=fitz.open(stream=data,filetype='pdf'); out['pages']=d.page_count
        out['text']=re.sub(r'\s+',' ',' '.join(d[p].get_text('text') for p in range(min(3,d.page_count)))).strip()[:6000]
    return out

out=[]
for label,name in candidates.items():
    x=fetch_pdf(BASE+name); x['expected']=label; out.append(x)
    print('FINAL_RECOVERY',json.dumps(x,ensure_ascii=False),flush=True)
open('eq_anomaly_probe.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
