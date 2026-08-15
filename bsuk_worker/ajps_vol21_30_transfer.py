from pathlib import Path
from urllib.parse import urljoin, urlparse
import csv, hashlib, json, re, requests
from bs4 import BeautifulSoup

INDEX = "https://biblicalstudies.gospelstudies.org.uk/articles_ajps_03.php"
ROOT = Path("out_ajps_21_30")
ROOT.mkdir(parents=True, exist_ok=True)
s = requests.Session()
s.headers.update({"User-Agent":"Mozilla/5.0 BSUK-Drive-Archiver/0.1"})
r = s.get(INDEX, timeout=120)
r.raise_for_status()
soup = BeautifulSoup(r.text, "html.parser")
summary = {}

headings = []
for tag in soup.find_all(["h2", "h3", "h4"]):
    txt = tag.get_text(" ", strip=True)
    m = re.match(r"Volume\s+(\d+)\s*\((\d{4})\)", txt, re.I)
    if m:
        vol, year = int(m.group(1)), int(m.group(2))
        if 21 <= vol <= 30:
            headings.append((vol, year, tag))

if not headings:
    raise RuntimeError("No Volume 21-30 headings found on current AJPS page")

for vol, year, start in headings:
    links = []
    node = start.find_next()
    while node is not None:
        if getattr(node, "name", None) in {"h2", "h3", "h4"}:
            t = node.get_text(" ", strip=True)
            if re.match(r"Volume\s+\d+\s*\(\d{4}\)", t, re.I):
                break
        if getattr(node, "name", None) == "a" and node.get("href"):
            href = urljoin(INDEX, node["href"])
            path = urlparse(href).path.lower()
            if path.endswith(".pdf"):
                context = node.parent.get_text(" ", strip=True) if node.parent else node.get_text(" ", strip=True)
                links.append((href, context))
        node = node.find_next()

    seen, uniq = set(), []
    for href, text in links:
        if href not in seen:
            seen.add(href)
            uniq.append((href, text))

    out = ROOT / f"Volume_{vol:02d}_{year}"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (href, text) in enumerate(uniq, 1):
        base = Path(urlparse(href).path).name or f"volume-{vol}-{i:03d}.pdf"
        name = base
        if (out / name).exists():
            name = f"{i:03d}-{base}"
        q = s.get(href, timeout=180, allow_redirects=True)
        q.raise_for_status()
        data = q.content
        if not data.startswith(b"%PDF-"):
            raise RuntimeError(f"Not PDF: vol={vol} url={href} final={q.url} type={q.headers.get('content-type')} bytes={len(data)}")
        (out / name).write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        rows.append((name, href, q.url, len(data), sha, text))
        print(f"VOL {vol} OK {name} bytes={len(data)} sha256={sha}")

    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "source_url", "final_url", "bytes", "sha256", "context"])
        w.writerows(rows)

    summary[str(vol)] = {"year": year, "pdf_count": len(rows), "files": [x[0] for x in rows]}
    print(f"VOL {vol} COMPLETE files={len(rows)}")

(ROOT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("ALL COMPLETE", json.dumps({k: v['pdf_count'] for k, v in summary.items()}))
