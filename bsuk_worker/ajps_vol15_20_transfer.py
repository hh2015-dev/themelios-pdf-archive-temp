from pathlib import Path
from urllib.parse import urljoin, urlparse
import csv, hashlib, json, requests
from bs4 import BeautifulSoup

INDEX = "https://biblicalstudies.gospelstudies.org.uk/articles_ajps_02.php"
ROOT = Path("out_ajps_15_20")
ROOT.mkdir(parents=True, exist_ok=True)
s = requests.Session()
s.headers.update({"User-Agent":"Mozilla/5.0 BSUK-Drive-Archiver/0.1"})
r = s.get(INDEX, timeout=120); r.raise_for_status()
soup = BeautifulSoup(r.text, "html.parser")
summary = {}

for vol in range(15, 21):
    start = next((h for h in soup.find_all("h3") if h.get_text(" ", strip=True).startswith(f"Volume {vol} ")), None)
    if start is None:
        raise RuntimeError(f"Volume {vol} heading not found")
    links=[]
    node=start.find_next()
    while node is not None:
        if getattr(node,"name",None)=="h3" and node.get_text(" ",strip=True).startswith(f"Volume {vol+1} "):
            break
        if getattr(node,"name",None)=="a" and node.get("href"):
            text=node.get_text(" ",strip=True)
            href=urljoin(INDEX,node["href"])
            path=urlparse(href).path.lower()
            if path.endswith(".pdf") and "complete issue" not in text.lower():
                links.append((href,text))
        node=node.find_next()
    seen=set(); uniq=[]
    for href,text in links:
        if href not in seen:
            seen.add(href); uniq.append((href,text))
    if not uniq:
        raise RuntimeError(f"No individual PDF links found for Volume {vol}")
    out=ROOT/f"Volume_{vol:02d}"
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,(href,text) in enumerate(uniq,1):
        base=Path(urlparse(href).path).name or f"volume-{vol}-{i:03d}.pdf"
        name=base
        if (out/name).exists():
            name=f"{i:03d}-{base}"
        q=s.get(href,timeout=120); q.raise_for_status(); data=q.content
        if not data.startswith(b"%PDF-"):
            raise RuntimeError(f"Not PDF: vol={vol} url={href} type={q.headers.get('content-type')} bytes={len(data)}")
        (out/name).write_bytes(data)
        sha=hashlib.sha256(data).hexdigest()
        rows.append((name,href,len(data),sha,text))
        print(f"VOL {vol} OK {name} bytes={len(data)} sha256={sha}")
    with (out/"manifest.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["filename","url","bytes","sha256","anchor_text"]); w.writerows(rows)
    summary[str(vol)]={"individual_pdf_count":len(rows),"files":[x[0] for x in rows]}
    print(f"VOL {vol} COMPLETE files={len(rows)}")
(ROOT/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print("ALL COMPLETE", json.dumps({k:v['individual_pdf_count'] for k,v in summary.items()}))
