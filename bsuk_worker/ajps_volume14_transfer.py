from pathlib import Path
from urllib.parse import urljoin, urlparse
import csv, hashlib, requests
from bs4 import BeautifulSoup

INDEX = "https://biblicalstudies.gospelstudies.org.uk/articles_ajps_02.php"
OUT = Path("out_ajps14")
OUT.mkdir(parents=True, exist_ok=True)
s = requests.Session()
s.headers.update({"User-Agent":"Mozilla/5.0 BSUK-Drive-Archiver/0.1"})
html = s.get(INDEX, timeout=120)
html.raise_for_status()
soup = BeautifulSoup(html.text, "html.parser")
start = next((h for h in soup.find_all("h3") if h.get_text(" ", strip=True).startswith("Volume 14")), None)
if start is None:
    raise RuntimeError("Volume 14 heading not found")
links=[]
node=start.find_next()
while node is not None:
    if getattr(node, "name", None)=="h3" and node.get_text(" ", strip=True).startswith("Volume 15"):
        break
    if getattr(node, "name", None)=="a" and node.get("href"):
        text=node.get_text(" ", strip=True)
        href=urljoin(INDEX,node["href"])
        if "/pdf/ajps/" in href and href.lower().endswith(".pdf") and "complete issue" not in text.lower():
            links.append((href,text))
    node=node.find_next()
# stable de-duplication
seen=set(); uniq=[]
for href,text in links:
    if href not in seen:
        seen.add(href); uniq.append((href,text))
if len(uniq)!=16:
    raise RuntimeError(f"Expected 16 individual Volume 14 PDFs, found {len(uniq)}: {[u for u,_ in uniq]}")
rows=[]
for href,text in uniq:
    name=Path(urlparse(href).path).name
    r=s.get(href, timeout=120)
    r.raise_for_status()
    data=r.content
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(f"Not PDF: {href}; type={r.headers.get('content-type')} bytes={len(data)}")
    (OUT/name).write_bytes(data)
    sha=hashlib.sha256(data).hexdigest()
    rows.append((name,href,len(data),sha,text))
    print(f"OK {name} bytes={len(data)} sha256={sha}")
with (OUT/"manifest.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["filename","url","bytes","sha256","anchor_text"]); w.writerows(rows)
print(f"COMPLETE files={len(rows)}")
