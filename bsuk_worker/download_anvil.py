import csv
import hashlib
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PAGES = [
    "https://biblicalstudies.gospelstudies.org.uk/articles_anvil_01.php",
    "https://biblicalstudies.gospelstudies.org.uk/articles_anvil_02.php",
    "https://biblicalstudies.gospelstudies.org.uk/articles_anvil_03.php",
]
OUT = Path("out_anvil")
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 BSUK-Drive-Archiver/0.2"}
MAX_WORKERS = 4


def get(url, stream=False):
    r = requests.get(url, headers=UA, timeout=90, stream=stream, allow_redirects=True)
    r.raise_for_status()
    return r


def clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("/", "-").replace("\\", "-").replace(":", " -")
    s = re.sub(r'[<>:"/\\|?*]', '', s)
    s = s.strip(" .-")
    return s


def parse_meta(label):
    label = re.sub(r"\s+", " ", label).strip()
    # Most citations: ... Anvil 12.3 (1995): 201-219. pdf
    m = re.search(r"(?:\bAnvil\s+)?(\d{1,2})\.(\d{1,2})\s*\((\d{4})\)\s*:\s*([0-9]+(?:\s*[-–]\s*[0-9]+)?)", label, re.I)
    if not m:
        return None
    vol, issue, year = map(int, m.group(1, 2, 3))
    pages = re.sub(r"\s+", "", m.group(4)).replace("–", "-")
    lead = label[:m.start()].strip(" ,.-")
    # Remove a trailing journal name if present before the parsed coordinates.
    lead = re.sub(r"\bAnvil\s*$", "", lead, flags=re.I).strip(" ,.-")
    lead = re.sub(r"\s*pdf\s*$", "", lead, flags=re.I).strip(" ,.-")
    return vol, issue, year, pages, lead


def discover():
    rows = []
    seen = set()
    for page in PAGES:
        r = get(page)
        page_copy = OUT / (Path(urlparse(page).path).name + ".html")
        page_copy.write_text(r.text, encoding="utf-8")
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urljoin(page, a["href"])
            p = urlparse(href)
            if "/pdf/anvil/" not in p.path.lower() or not p.path.lower().endswith(".pdf"):
                continue
            if href in seen:
                continue
            seen.add(href)
            label = " ".join(a.stripped_strings)
            meta = parse_meta(label)
            if not meta:
                rows.append({"source_page": page, "source_url": href, "label": label, "status": "METADATA_UNRESOLVED"})
                continue
            vol, issue, year, pages, lead = meta
            base = f"Anvil - Volume {vol:03d} - Issue {issue:02d} - {year} - pp {pages}"
            if lead:
                base += " - " + clean(lead)
            # Keep within safe filesystem/Drive name limits while retaining metadata.
            base = clean(base)
            if len(base) > 210:
                base = base[:210].rstrip(" .-")
            filename = base + ".pdf"
            rel = Path(f"Volume {vol:03d} - {year}") / f"Issue {issue:02d}" / filename
            rows.append({
                "volume": vol, "issue": issue, "year": year, "pages": pages,
                "source_page": page, "source_url": href, "label": label,
                "filename": filename, "relative_path": str(rel), "status": "DISCOVERED"
            })
    return rows


def download_one(row):
    if row.get("status") != "DISCOVERED":
        return row
    dest = OUT / row["relative_path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        rr = get(row["source_url"], stream=True)
        h = hashlib.sha256(); n = 0
        with open(dest, "wb") as f:
            for chunk in rr.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk); h.update(chunk); n += len(chunk)
        with open(dest, "rb") as f:
            magic = f.read(5)
        if magic != b"%PDF-":
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"not PDF magic: {magic!r}")
        row["bytes"] = n
        row["sha256"] = h.hexdigest()
        row["status"] = "OK"
    except Exception as e:
        row["bytes"] = 0
        row["sha256"] = ""
        row["status"] = "ERROR:" + repr(e)
    return row


def write_manifest(rows):
    fields = ["volume","issue","year","pages","source_page","source_url","label","filename","relative_path","bytes","sha256","status"]
    with open(OUT / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main():
    rows = discover()
    discovered = sum(1 for r in rows if r.get("status") == "DISCOVERED")
    unresolved = sum(1 for r in rows if r.get("status") == "METADATA_UNRESOLVED")
    print("DISCOVERED", discovered, "UNRESOLVED", unresolved)
    if not discovered:
        write_manifest(rows)
        return 3
    completed = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(download_one, r) for r in rows]
        for fut in as_completed(futs):
            r = fut.result(); completed.append(r)
            if r.get("status") == "OK":
                print("OK", r.get("volume"), r.get("issue"), r.get("year"), r.get("bytes"), r.get("filename"))
            else:
                print("NOT_OK", r.get("source_url"), r.get("status"))
    completed.sort(key=lambda r: (int(r.get("volume") or 999), int(r.get("issue") or 999), int(str(r.get("pages") or "999").split("-")[0] or 999), r.get("filename", "")))
    write_manifest(completed)
    ok = sum(1 for r in completed if r.get("status") == "OK")
    errors = sum(1 for r in completed if str(r.get("status", "")).startswith("ERROR"))
    unresolved = sum(1 for r in completed if r.get("status") == "METADATA_UNRESOLVED")
    print("SUMMARY", "OK", ok, "ERRORS", errors, "UNRESOLVED", unresolved)
    return 0 if ok and not errors and not unresolved else 4


if __name__ == "__main__":
    sys.exit(main())
