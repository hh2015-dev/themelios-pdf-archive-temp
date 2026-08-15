from __future__ import annotations

import csv
import hashlib
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PAGES = {
    "1": "https://biblicalstudies.gospelstudies.org.uk/articles_ajet-01.php",
    "2": "https://biblicalstudies.gospelstudies.org.uk/articles_ajet-02.php",
    "3": "https://biblicalstudies.gospelstudies.org.uk/articles_ajet-03.php",
    "4": "https://biblicalstudies.gospelstudies.org.uk/articles_ajet-04.php",
}

batch = sys.argv[1] if len(sys.argv) > 1 else "1"
if batch not in PAGES:
    raise SystemExit(f"Unknown batch: {batch}")

page_url = PAGES[batch]
out_dir = Path("bsuk_output") / "ajet" / f"batch-{batch}"
out_dir.mkdir(parents=True, exist_ok=True)
manifest_path = out_dir / "manifest.csv"

session = requests.Session()
session.headers.update({"User-Agent": "BSUK-Drive-Archiver/0.1 (+archival validation)"})

r = session.get(page_url, timeout=60)
r.raise_for_status()
soup = BeautifulSoup(r.text, "html.parser")

links: list[tuple[str, str]] = []
seen: set[str] = set()
for a in soup.find_all("a", href=True):
    text = " ".join(a.get_text(" ", strip=True).split())
    if "complete issue" not in text.lower():
        continue
    url = urljoin(page_url, a["href"])
    if url in seen:
        continue
    seen.add(url)
    links.append((text, url))

if not links:
    raise SystemExit(f"No Complete Issue links discovered at {page_url}")

rows = []
for idx, (label, url) in enumerate(links, 1):
    parsed = urlparse(url)
    source_name = os.path.basename(parsed.path) or f"issue-{idx:03d}.pdf"
    if not source_name.lower().endswith(".pdf"):
        source_name += ".pdf"
    # Keep original basename; uniqueness guard if source repeats a basename.
    dest = out_dir / source_name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        dest = out_dir / f"{stem}-{idx:03d}{suffix}"

    resp = session.get(url, timeout=180)
    resp.raise_for_status()
    data = resp.content
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(f"Not a PDF: {url} ({resp.headers.get('content-type')})")
    dest.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()

    m = re.search(r"(\d{1,2})[-_](\d{1,2})", source_name)
    volume = int(m.group(1)) if m else ""
    issue = int(m.group(2)) if m else ""
    rows.append({
        "batch": batch,
        "page_url": page_url,
        "label": label,
        "source_url": url,
        "source_filename": source_name,
        "volume": volume,
        "issue": issue,
        "bytes": len(data),
        "sha256": sha,
        "status": "OK",
    })
    print(f"OK {idx}/{len(links)} {source_name} {len(data)} {sha}", flush=True)

with manifest_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

print(f"SUMMARY batch={batch} complete_issue_links={len(links)} downloaded={len(rows)}")
