import json, requests
S=requests.Session();S.headers['User-Agent']='BSUK-Ashland-Search/7.0'
queries={
 'ALL_ASHLAND':'title:"Ashland Theological"',
 'VOL11':'title:"Ashland Theological Bulletin" AND (1978 OR volume:11 OR volume:"Vol. 11")',
 'EARLY':'title:"Ashland Theological Bulletin" AND (1968 OR 1969 OR 1970 OR 1971 OR 1972 OR 1973)',
 'MID':'title:"Ashland Theological Journal" AND (1999 OR 2000 OR 2001 OR 2002 OR 2003 OR 2004)',
}
for label,q in queries.items():
    try:
        r=S.get('https://archive.org/advancedsearch.php',params={'q':q,'fl[]':['identifier','title','date','year','volume','collection','mediatype'],'rows':200,'page':1,'output':'json'},timeout=30)
        print('HTTP',label,r.status_code,r.url,flush=True)
        r.raise_for_status()
        docs=r.json().get('response',{}).get('docs',[])
        print('SEARCH|'+label+'|'+json.dumps(docs,ensure_ascii=False),flush=True)
    except Exception as e: print('ERROR|'+label+'|'+repr(e),flush=True)
