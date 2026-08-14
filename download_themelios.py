import csv
import re
import shutil
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ARCHIVE_URL = "https://www.thegospelcoalition.org/themelios/issues/"
OUT = Path("output")
BATCH_SIZE = 15
MONTHS = "January February March April May June July August September October November December".split()
DATE_RE = re.compile(r"(" + "|".join(MONTHS) + r")\s+(19|20)\d{2}")
VOL_RE = re.compile(r"\bVolume\s+(\d+)\b", re.I)
ISSUE_RE = re.compile(r"\bIssue\s+(\d+)\b", re.I)


def find_metadata(link):
    node = link
    for _ in range(10):
        node = node.parent
        if node is None:
            break
        text = " ".join(node.stripped_strings)
        d = DATE_RE.search(text)
        v = VOL_RE.search(text)
        i = ISSUE_RE.search(text)
        if d and v and i:
            month, year = d.group(1), d.group(0).split()[-1]
            return int(v.group(1)), int(i.group(1)), int(year), month
    return None


def main():
    r = requests.get(ARCHIVE_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    issues = []
    seen = set()
    for a in soup.find_all("a", href=True):
        if a.get_text(" ", strip=True).upper() != "PDF":
            continue
        href = urljoin(ARCHIVE_URL, a["href"])
        if ".pdf" not in href.lower():
            continue
        meta = find_metadata(a)
        if not meta:
            raise RuntimeError(f"Could not extract date/volume/issue for {href}")
        vol, issue, year, month = meta
        key = (vol, issue)
        if key in seen:
            continue
        seen.add(key)
        filename = f"Themelios Vol {vol} No {issue} {year} {month}.pdf"
        issues.append({"volume": vol, "issue": issue, "year": year, "month": month, "url": href, "filename": filename})

    issues.sort(key=lambda x: (x["volume"], x["issue"]))
    if len(issues) < 140:
        raise RuntimeError(f"Archive discovery unexpectedly found only {len(issues)} PDF issues")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["volume", "issue", "year", "month", "filename", "url"])
        w.writeheader()
        w.writerows(issues)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for idx, item in enumerate(issues):
        batch = idx // BATCH_SIZE
        d = OUT / f"batch-{batch:02d}"
        d.mkdir(exist_ok=True)
        dest = d / item["filename"]
        print(f"[{idx+1}/{len(issues)}] {item['filename']}", flush=True)
        with session.get(item["url"], timeout=120, stream=True, allow_redirects=True) as resp:
            resp.raise_for_status()
            with dest.open("wb") as out:
                for chunk in resp.iter_content(1024 * 1024):
                    if chunk:
                        out.write(chunk)
        size = dest.stat().st_size
        if size < 50_000:
            raise RuntimeError(f"Downloaded file is unexpectedly small: {dest} ({size} bytes)")
        with dest.open("rb") as f:
            if f.read(5) != b"%PDF-":
                raise RuntimeError(f"Not a PDF: {dest}")

    print(f"DONE: {len(issues)} issues in {(len(issues)+BATCH_SIZE-1)//BATCH_SIZE} batches")


if __name__ == "__main__":
    main()
