from pathlib import Path
import csv
import hashlib
import requests

BASE = "https://biblicalstudies.gospelstudies.org.uk/pdf/ajps/"
FILES = [
    "ajps-13-1_001.pdf",
    "ajps-13-1_003.pdf",
    "ajps-13-1_020.pdf",
    "ajps-13-1_041.pdf",
    "ajps-13-1_065.pdf",
    "ajps-13-1_098.pdf",
    "ajps-13-1_125.pdf",
    "ajps-13-2_165.pdf",
    "ajps-13-2_167.pdf",
    "ajps-13-2_180.pdf",
    "ajps-13-2_203.pdf",
    "ajps-13-2_217.pdf",
    "ajps-13-2_257.pdf",
    "ajps-13-2_282.pdf",
    "ajps-13-2_301.pdf",
]
OUTDIR = Path("out_ajps13")
OUTDIR.mkdir(parents=True, exist_ok=True)
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 BSUK-Drive-Archiver/0.1"})
rows = []
for name in FILES:
    url = BASE + name
    r = s.get(url, timeout=120)
    r.raise_for_status()
    data = r.content
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(f"Not a PDF: {url} content-type={r.headers.get('content-type')} bytes={len(data)}")
    path = OUTDIR / name
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    rows.append((name, url, len(data), sha))
    print(f"OK {name} bytes={len(data)} sha256={sha}")
with (OUTDIR / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["filename", "url", "bytes", "sha256"])
    w.writerows(rows)
print(f"COMPLETE files={len(rows)}")
