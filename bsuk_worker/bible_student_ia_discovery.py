import json,re,time
from pathlib import Path
from urllib.parse import quote, unquote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

OUT=Path('bible_student_ia_discovery'); OUT.mkdir(exist_ok=True)
queries=[
 '"The Bible Student" "Alfred McDonald Redwood"',
 '"The Bible Student" Mysore',
 '"The Bible Student" Bangalore',
 '"Recent Finds in Palestine"',
 '"Exegetical Study of Colossians" "Bible Student"',
 '"The Bible Student" "Scripture Literature Press"',
]
opts=Options(); opts.add_argument('--headless=new'); opts.add_argument('--no-sandbox'); opts.add_argument('--disable-dev-shm-usage'); opts.add_argument('--disable-gpu'); opts.add_argument('--window-size=1400,1200')
driver=webdriver.Chrome(options=opts)
JS=r'''
function walk(root, out) {
  if (!root || !root.querySelectorAll) return;
  root.querySelectorAll('a[href]').forEach(a => out.push({href:a.href, text:(a.innerText||a.textContent||'').trim()}));
  root.querySelectorAll('*').forEach(el => { if (el.shadowRoot) walk(el.shadowRoot, out); });
}
let out=[]; walk(document,out); return out;
'''
results=[]
try:
  for q in queries:
    url='https://archive.org/search?query='+quote(q)+'&sin=TXT'
    driver.get(url)
    # allow JS search results to hydrate; stop early once detail links appear
    links=[]
    for _ in range(12):
      time.sleep(1)
      try: links=driver.execute_script(JS) or []
      except Exception: links=[]
      if any('/details/' in (x.get('href') or '') for x in links): break
    ids=[]; matches=[]
    for x in links:
      href=x.get('href') or ''; m=re.search(r'/details/([^?/#]+)',href)
      if not m: continue
      ident=unquote(m.group(1))
      if ident not in ids:
        ids.append(ident); matches.append({'identifier':ident,'href':href,'text':x.get('text','')})
    results.append({'query':q,'url':driver.current_url,'title':driver.title,'identifiers':ids[:100],'matches':matches[:100],'html_bytes':len(driver.page_source)})
finally:
  driver.quit()
summary={'queries':results,'unique_identifiers':sorted({i for r in results for i in r['identifiers']})}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
