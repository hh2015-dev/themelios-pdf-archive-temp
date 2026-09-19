import json, urllib.parse, urllib.request

KEY="DVQyidFLOAjp12ib92pNJPmflmB5IessOq1CJQDK"
BASE="https://api.nli.org.il/openlibrary"

def get(path, params=None):
    q=urllib.parse.urlencode(params or {}, doseq=True)
    url=BASE+path+("?" + q if q else "")
    req=urllib.request.Request(url, headers={"User-Agent":"NLI-Catalog-Harvester/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body=r.read().decode("utf-8","replace")
        return r.status, dict(r.headers), body

s,h,b=get("/values/getRulesOfQuery",{"api_key":KEY})
print("RULES",s,h.get("X-RateLimit-Remaining"))
rules=json.loads(b)
print("LANGS",len(rules.get("LANGUAGE",[])))

params={
 "api_key":KEY,
 "query":"language,exact,eng",
 "material_type":"books",
 "availability_type":"online_access",
 "output_format":"json",
 "items_per_page":2,
 "result_page":1
}
s,h,b=get("/search",params)
print("SEARCH",s,h.get("X-RateLimit-Remaining"))
print(b[:12000])
