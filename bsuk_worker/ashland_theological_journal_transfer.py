from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor
import csv, hashlib, json, re, time
import requests
from bs4 import BeautifulSoup

PAGES = [
    "https://biblicalstudies.gospelstudies.org.uk/articles_ashland-theological-journal_01.php",
    "https://biblicalstudies.gospelstudies.org.uk/articles_ashland-theological-journal_02.php",
    "https://biblicalstudies.gospelstudies.org.uk/articles_ashland-theological-journal_03.php",
]
ROOT = Path("out_ashland_theological_journal")
ROOT.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 BSUK-Drive-Archiver/0.1"}


def get(url, timeout=180):
    last = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            if attempt < 3:
                time.sleep(attempt * 2)
    raise last


def safe_label(text):
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    return text.strip("_") or "unknown"


def collect_volumes(index_url):
    r = get(index_url, 120)
    soup = BeautifulSoup(r.text, "html.parser")
    volumes = []
    for tag in soup.find_all(["h2", "h3", "h4"]):
        txt = tag.get_text(" ", strip=True)
        m = re.match(r"Volume\s+(\d+)\s*\(([^)]+)\)", txt, re.I)
        if not m:
            continue
        vol = int(m.group(1))
        label = m.group(2).strip()
        links = []
        node = tag.find_next()
        while node is not None:
            if getattr(node, "name", None) in {"h2", "h3", "h4"}:
                t = node.get_text(" ", strip=True)
                if re.match(r"Volume\s+\d+\s*\([^)]+\)", t, re.I):
                    break
            if getattr(node, "name", None) == "a" and node.get("href"):
                href = urljoin(index_url, node["href"])
                if urlparse(href).path.lower().endswith(".pdf"):
                    context = node.parent.get_text(" ", strip=True) if node.parent else node.get_text(" ", strip=True)
                    links.append((href, context))
            node = node.find_next()
        seen = set()
        uniq = []
        for href, context in links:
            if href not in seen:
                seen.add(href)
                uniq.append((href, context))
        volumes.append((vol, label, uniq, index_url))
    return volumes


def download_one(args):
    i, href, context, out = args
    r = get(href, 240)
    data = r.content
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(
            f"Not PDF: url={href} final={r.url} type={r.headers.get('content-type')} bytes={len(data)}"
        )
    base = Path(unquote(urlparse(r.url).path)).name or Path(unquote(urlparse(href).path)).name or f"file-{i:03d}.pdf"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    path = out / base
    if path.exists():
        base = f"{i:03d}-{base}"
        path = out / base
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    return i, base, href, r.url, len(data), sha, context


all_volumes = []
for page in PAGES:
    all_volumes.extend(collect_volumes(page))

# Keep the first occurrence of each volume heading across the three index pages.
by_vol = {}
for vol, label, links, page in all_volumes:
    if vol not in by_vol or (not by_vol[vol][1] and links):
        by_vol[vol] = (label, links, page)

summary = {}
for vol in sorted(by_vol):
    label, links, page = by_vol[vol]
    out = ROOT / f"Volume_{vol:03d}_{safe_label(label)}"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    if links:
        tasks = [(i, href, context, out) for i, (href, context) in enumerate(links, 1)]
        with ThreadPoolExecutor(max_workers=4) as ex:
            for result in ex.map(download_one, tasks):
                rows.append(result)
                print(f"VOL {vol} OK {result[1]} bytes={result[4]} sha256={result[5]}")
        rows.sort(key=lambda x: x[0])
    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["order", "filename", "source_url", "final_url", "bytes", "sha256", "context"])
        w.writerows(rows)
    summary[str(vol)] = {
        "label": label,
        "source_page": page,
        "pdf_count": len(rows),
        "files": [r[1] for r in rows],
    }
    print(f"VOL {vol} COMPLETE files={len(rows)}")

(ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print("ALL COMPLETE", json.dumps({k: v["pdf_count"] for k, v in summary.items()}))
print("TOTAL PDF", sum(v["pdf_count"] for v in summary.values()))
