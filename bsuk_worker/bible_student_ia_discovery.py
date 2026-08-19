import json,time
from pathlib import Path
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True)
q='"Recent Finds in Palestine"'
opts=Options(); opts.add_argument('--headless=new'); opts.add_argument('--no-sandbox'); opts.add_argument('--disable-dev-shm-usage'); opts.add_argument('--disable-gpu'); opts.add_argument('--window-size=1400,1200')
opts.set_capability('goog:loggingPrefs', {'performance':'ALL','browser':'ALL'})
driver=webdriver.Chrome(options=opts)
try:
    url='https://archive.org/search?query='+quote(q)+'&sin=TXT'
    driver.get(url); time.sleep(15)
    perf=driver.get_log('performance')
    browser=driver.get_log('browser')
    reqs=[]
    for entry in perf:
        try:
            msg=json.loads(entry['message'])['message']
            if msg.get('method')!='Network.requestWillBeSent': continue
            r=msg['params']['request']; u=r.get('url','')
            if 'archive.org' in u or 'internetarchive' in u:
                reqs.append({'url':u,'method':r.get('method'),'type':msg['params'].get('type'),'postData':r.get('postData')})
        except Exception: pass
    # ordered de-dupe
    seen=set(); uniq=[]
    for r in reqs:
        sig=(r['url'],r['method'],r.get('postData'))
        if sig in seen: continue
        seen.add(sig); uniq.append(r)
    result={'query':q,'page_url':driver.current_url,'title':driver.title,'network_requests':uniq,'browser_log':browser,'html_bytes':len(driver.page_source)}
finally:
    driver.quit()
(OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
