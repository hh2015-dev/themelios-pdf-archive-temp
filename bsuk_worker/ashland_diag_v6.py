import json, re, requests, time, xml.etree.ElementTree as ET
S=requests.Session();S.headers['User-Agent']='BSUK-Ashland-Diag/6.0'

def get(url):
    last=None
    for k in range(8):
        try:
            r=S.get(url,timeout=(20,90),allow_redirects=True)
            if r.status_code==200:return r
            last=(r.status_code,r.url,r.text[:200])
            r.close()
        except Exception as e:last=repr(e)
        time.sleep(2+k)
    raise RuntimeError(f'{url}: {last}')

def files_xml(ident):
    url=f'https://archive.org/download/{ident}/{ident}_files.xml'
    try:
        r=get(url); print(f'FILES_XML|{ident}|url={r.url}|bytes={len(r.content)}',flush=True)
        root=ET.fromstring(r.content);r.close()
        for f in root.findall('file'):
            name=f.attrib.get('name','');fmt=(f.findtext('format') or '');size=f.findtext('size') or '';src=f.attrib.get('source','');private=f.findtext('private') or ''
            if any(x in name.lower() for x in ['pdf','jp2','djvu','text','torrent','abbyy','scandata']) or any(x in fmt.lower() for x in ['pdf','jp2','djvu','text','torrent']):
                print('XF|'+json.dumps({'id':ident,'name':name,'format':fmt,'size':size,'source':src,'private':private}),flush=True)
    except Exception as e:print(f'FILES_XML_ERROR|{ident}|{repr(e)}',flush=True)

def search(q,label):
    params={'q':q,'fl[]':['identifier','title','date','year','volume'],'rows':100,'page':1,'output':'json'}
    last=None
    for k in range(6):
        try:
            r=S.get('https://archive.org/advancedsearch.php',params=params,timeout=90);r.raise_for_status();docs=r.json().get('response',{}).get('docs',[]);r.close()
            print('SEARCH|'+label+'|'+json.dumps(docs,ensure_ascii=False),flush=True);return
        except Exception as e:last=e;time.sleep(2+k)
    print(f'SEARCH_ERROR|{label}|{repr(last)}',flush=True)

def main():
    for ident in ['ashlandtheologic1161alde','ashlandtheologic3136bake']:
        files_xml(ident)
    search('title:"Ashland Theological Bulletin" AND (date:1978 OR year:1978 OR volume:11)','VOL11')
    search('title:"Ashland Theological Bulletin" AND (date:1968 OR date:1969 OR date:1970 OR date:1971 OR date:1972 OR date:1973)','VOLS1_6')
    search('title:"Ashland Theological Journal" AND (date:1999 OR date:2000 OR date:2001 OR date:2002 OR date:2003 OR date:2004)','VOLS31_36')
if __name__=='__main__':main()
