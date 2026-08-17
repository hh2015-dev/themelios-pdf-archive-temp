import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import fitz  # PyMuPDF
import requests

SEARCH_URL = "https://archive.org/advancedsearch.php"
META_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{name}"
OUT_DIR = Path("ashland_inventory")
OUT_DIR.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({"User-Agent": "BSUK-Ashland-Inventory/1.0"})


def get_json(url, **kwargs):
    last = None
    for attempt in range(5):
        try:
            r = session.get(url, timeout=90, **kwargs)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET JSON failed: {url}: {last}")


def download(url, dest):
    last = None
    for attempt in range(4):
        try:
            with session.get(url, stream=True, timeout=(30, 180)) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)
            return
        except Exception as e:
            last = e
            try:
                os.remove(dest)
            except OSError:
                pass
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Download failed: {url}: {last}")


def roman(n):
    vals = [(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[-1]


def normalize_text(s):
    s = s.upper().replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"\s+", " ", s)
    return s


def parse_volume_range(value):
    if not value:
        return None
    if isinstance(value, list):
        value = " ".join(str(x) for x in value)
    nums = [int(x) for x in re.findall(r"\d+", str(value)) if 1 <= int(x) <= 42]
    if len(nums) >= 2:
        return min(nums), max(nums)
    if len(nums) == 1:
        return nums[0], nums[0]
    # Roman fallback from metadata strings such as Vol. XXXI-XXXVI.
    toks = re.findall(r"\b[IVXLCDM]{1,8}\b", str(value).upper())
    def r2i(t):
        m = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}
        total = prev = 0
        for ch in reversed(t):
            v = m[ch]
            total += -v if v < prev else v
            prev = max(prev, v)
        return total
    vals = [r2i(t) for t in toks]
    vals = [x for x in vals if 1 <= x <= 42]
    if vals:
        return min(vals), max(vals)
    return None


def pick_pdf(files, identifier):
    pdfs = []
    for f in files:
        name = f.get("name", "")
        if not name.lower().endswith(".pdf"):
            continue
        if f.get("private") is True:
            continue
        fmt = str(f.get("format", ""))
        size = int(f.get("size") or 0)
        score = 0
        if name == f"{identifier}.pdf": score += 1000
        if "Text PDF" in fmt: score += 500
        if f.get("source") == "derivative": score += 50
        if "searchable" in name.lower(): score += 20
        if "bw.pdf" in name.lower(): score -= 200
        pdfs.append((score, size, name, fmt))
    if not pdfs:
        return None
    pdfs.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return pdfs[0]


def discover_items():
    q = 'collection:brethrendigitalarchives AND (title:"Ashland Theological Bulletin" OR title:"Ashland Theological Journal")'
    params = {
        "q": q,
        "fl[]": ["identifier", "title", "volume", "date"],
        "rows": 100,
        "page": 1,
        "output": "json",
    }
    data = get_json(SEARCH_URL, params=params)
    docs = data.get("response", {}).get("docs", [])
    if not docs:
        params["q"] = 'collection:brethrendigitalarchives AND title:(Ashland Theological)'
        data = get_json(SEARCH_URL, params=params)
        docs = data.get("response", {}).get("docs", [])
    found = []
    for d in docs:
        title = str(d.get("title", ""))
        if "Ashland Theological" not in title:
            continue
        ident = d.get("identifier")
        if not ident:
            continue
        meta = get_json(META_URL.format(identifier=ident))
        md = meta.get("metadata", {})
        vr = parse_volume_range(md.get("volume") or d.get("volume"))
        if not vr:
            continue
        chosen = pick_pdf(meta.get("files", []), ident)
        if not chosen:
            continue
        score, source_size, pdf_name, fmt = chosen
        found.append({
            "identifier": ident,
            "title": md.get("title") or title,
            "volume_raw": md.get("volume") or d.get("volume"),
            "vstart": vr[0], "vend": vr[1],
            "pdf_name": pdf_name,
            "source_size": source_size,
            "format": fmt,
        })
    # Dedupe exact ranges; prefer canonical identifier.pdf / largest useful PDF score already selected.
    by_range = {}
    for x in found:
        key = (x["vstart"], x["vend"])
        if key not in by_range or x["source_size"] > by_range[key]["source_size"]:
            by_range[key] = x
    return sorted(by_range.values(), key=lambda x: x["vstart"])


def page_texts(doc):
    texts = []
    for i in range(doc.page_count):
        try:
            texts.append(normalize_text(doc.load_page(i).get_text("text")))
        except Exception:
            texts.append("")
    return texts


def marker_score(text, n):
    if not text:
        return 0
    target = roman(n)
    score = 0
    # Strong Arabic-number article/header marker.
    if re.search(rf"ASHLAND\s+THEOLOGICAL\s+(?:JOURNAL|BULLETIN)\s+0*{n}\b", text):
        score = max(score, 90)
    # Roman VOLUME marker, tolerant of one OCR substitution such as XXXVl for XXXVI.
    for tok in re.findall(r"\bVOLUME\s+([IVXL1]{1,8})\b", text):
        clean = tok.replace("1", "I")
        if clean == target:
            score = max(score, 100)
        elif edit_distance(clean, target) <= 1:
            score = max(score, 95)
    return score


def infer_year(text):
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20[01]\d)\b", text)]
    years = [y for y in years if 1968 <= y <= 2010]
    if not years:
        return None
    # Prefer the most frequent year on a title/contents page.
    return max(sorted(set(years)), key=years.count)


def locate_starts(texts, vstart, vend):
    raw_markers = {}
    for n in range(vstart, vend + 1):
        hits = []
        for i, t in enumerate(texts):
            s = marker_score(t, n)
            if s:
                hits.append((s, i))
        if not hits:
            raw_markers[n] = None
            continue
        best_score = max(s for s, _ in hits)
        raw_markers[n] = min(i for s, i in hits if s == best_score)

    # Fill missing markers by detecting distinct journal title/contents pages in sequence.
    title_candidates = []
    for i, t in enumerate(texts):
        if "ASHLAND" in t and "THEOLOGICAL" in t and ("JOURNAL" in t or "BULLETIN" in t):
            y = infer_year(t)
            if y is not None and ("CONTENTS" in t or "ASHLAND, OHIO" in t):
                title_candidates.append((i, y))
    # Deduplicate runs: first candidate for each year/run.
    dedup = []
    for i, y in title_candidates:
        if dedup and y == dedup[-1][1] and i - dedup[-1][0] <= 12:
            continue
        dedup.append((i, y))

    known = [raw_markers[n] for n in range(vstart, vend + 1)]
    if any(x is None for x in known) and len(dedup) >= (vend - vstart + 1):
        # Order-based fallback only for missing markers.
        seq = dedup[:vend - vstart + 1]
        for off, n in enumerate(range(vstart, vend + 1)):
            if raw_markers[n] is None:
                raw_markers[n] = seq[off][0]

    if any(raw_markers[n] is None for n in range(vstart, vend + 1)):
        missing = [n for n in range(vstart, vend + 1) if raw_markers[n] is None]
        raise RuntimeError(f"Could not locate volume markers: {missing}")

    # Require strict increasing order.
    marker_pages = [raw_markers[n] for n in range(vstart, vend + 1)]
    if marker_pages != sorted(marker_pages) or len(set(marker_pages)) != len(marker_pages):
        raise RuntimeError(f"Non-monotonic volume markers: {raw_markers}")

    starts = {}
    years = {}
    for n in range(vstart, vend + 1):
        m = raw_markers[n]
        window = range(max(0, m - 12), m + 1)
        marker_year = infer_year(texts[m])
        candidates = []
        for j in window:
            t = texts[j]
            if "ASHLAND" not in t or "THEOLOGICAL" not in t or not ("JOURNAL" in t or "BULLETIN" in t):
                continue
            y = infer_year(t)
            if marker_year is None or y == marker_year:
                candidates.append(j)
        starts[n] = min(candidates) if candidates else m
        years[n] = marker_year or infer_year(texts[starts[n]])

    # If backtracking crossed into prior volume, enforce increasing starts; fall back to marker page.
    prev = -1
    for n in range(vstart, vend + 1):
        if starts[n] <= prev:
            starts[n] = raw_markers[n]
        prev = starts[n]
    return starts, years, raw_markers


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    items = discover_items()
    print("DISCOVERED_BUNDLES=" + json.dumps(items, ensure_ascii=False), flush=True)
    coverage = []
    for x in items:
        coverage.extend(range(x["vstart"], x["vend"] + 1))
    if sorted(set(coverage)) != list(range(1, 43)):
        print("WARNING_COVERAGE=" + json.dumps(sorted(set(coverage))), flush=True)

    rows = []
    with tempfile.TemporaryDirectory(prefix="ashland_inventory_") as td:
        td = Path(td)
        for item in items:
            ident = item["identifier"]
            src = td / f"{ident}.pdf"
            url = DOWNLOAD_URL.format(identifier=quote(ident), name=quote(item["pdf_name"]))
            print(f"BUNDLE_START|{item['vstart']}-{item['vend']}|{ident}|source_bytes={item['source_size']}|{url}", flush=True)
            download(url, src)
            actual_source = src.stat().st_size
            print(f"BUNDLE_DOWNLOADED|{ident}|bytes={actual_source}", flush=True)
            doc = fitz.open(src)
            texts = page_texts(doc)
            starts, years, markers = locate_starts(texts, item["vstart"], item["vend"])
            vols = list(range(item["vstart"], item["vend"] + 1))
            for idx, n in enumerate(vols):
                start = starts[n]
                end = (starts[vols[idx+1]] - 1) if idx + 1 < len(vols) else doc.page_count - 1
                if end < start:
                    raise RuntimeError(f"Invalid range for volume {n}: {start}-{end}")
                out = td / f"Ashland_Theological_Volume_{n:02d}.pdf"
                part = fitz.open()
                part.insert_pdf(doc, from_page=start, to_page=end)
                part.save(out, garbage=4, deflate=True, clean=True)
                part.close()
                size = out.stat().st_size
                row = {
                    "volume": n,
                    "year": years.get(n),
                    "size_bytes": size,
                    "size_mib": round(size / 1048576, 2),
                    "pages": end - start + 1,
                    "bundle_identifier": ident,
                    "source_pdf": item["pdf_name"],
                    "source_pdf_bytes": actual_source,
                    "start_page_1based": start + 1,
                    "end_page_1based": end + 1,
                    "marker_page_1based": markers[n] + 1,
                    "sha256": sha256_file(out),
                }
                rows.append(row)
                print("RESULT|" + "|".join([
                    str(n), str(row["year"] or ""), str(size), f"{row['size_mib']:.2f}",
                    str(row["pages"]), ident, f"{start+1}-{end+1}", row["sha256"]
                ]), flush=True)
                out.unlink()
            doc.close()
            src.unlink()
            print(f"BUNDLE_DONE|{ident}", flush=True)

    rows.sort(key=lambda r: r["volume"])
    with open(OUT_DIR / "ashland_inventory.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    if rows:
        with open(OUT_DIR / "ashland_inventory.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    with open(OUT_DIR / "ashland_inventory.md", "w", encoding="utf-8") as f:
        f.write("| Volume | Year | Size MiB | Bytes | Pages | Bundle |\n|---:|---:|---:|---:|---:|---|\n")
        for r in rows:
            f.write(f"| {r['volume']} | {r['year'] or ''} | {r['size_mib']:.2f} | {r['size_bytes']} | {r['pages']} | {r['bundle_identifier']} |\n")
    print(f"FINAL_COUNT={len(rows)}", flush=True)
    if len(rows) != 42:
        raise SystemExit(f"Expected 42 volume rows, got {len(rows)}")


if __name__ == "__main__":
    main()
