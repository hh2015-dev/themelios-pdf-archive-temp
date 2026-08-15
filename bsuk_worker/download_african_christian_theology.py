import csv, hashlib, re, sys, unicodedata
from pathlib import Path
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

BASES = [
    "https://biblicalstudies.gospelstudies.org.uk/",
    "https://www.biblicalstudies.org.uk/",
]
OUT = Path("out_african_christian_theology")
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 BSUK-Drive-Archiver/0.2"}
JOURNAL_NAMES = r"(?:African Christian Theology|Théologie Chrétienne Africaine|Teologia Cristã Africana)"


def get(url, stream=False):
    r = requests.get(url, headers=UA, timeout=60, stream=stream, allow_redirects=True)
    r.raise_for_status()
    return r


def discover_page():
    diagnostics = []
    for base in BASES:
        for entry in ("articles.php", "sitemap.php"):
            url = urljoin(base, entry)
            try:
                r = get(url)
                text = r.text
                soup = BeautifulSoup(text, "html.parser")
                for tag in soup.find_all(["option", "a"]):
                    label = " ".join(tag.stripped_strings)
                    if "African Christian Theology" in label:
                        href = tag.get("value") if tag.name == "option" else tag.get("href")
                        diagnostics.append((url, tag.name, label, href or ""))
                        if href and href not in ("#", ""):
                            candidate = urljoin(url, href)
                            if "african-christian-theology" in candidate.lower():
                                return candidate, diagnostics
                m = re.search(r'(?is)(?:href|value)=["\']([^"\']+)["\'][^>]{0,300}>?[^<]{0,120}African Christian Theology', text)
                if m:
                    return urljoin(url, m.group(1)), diagnostics
                m = re.search(r'(?is)African Christian Theology.{0,400}?(?:href|value)=["\']([^"\']+)["\']', text)
                if m:
                    return urljoin(url, m.group(1)), diagnostics
            except Exception as e:
                diagnostics.append((url, "ERROR", repr(e), ""))
    return None, diagnostics


def normalize_month_date(s):
    s = re.sub(r"\s+", " ", s.strip())
    repl = {
        "Sept.": "September", "Sep.": "September", "Sept": "September",
        "Oct.": "October", "Oct": "October",
        "Mar.": "March", "Mar": "March",
    }
    for a, b in repl.items():
        if s.startswith(a + " "):
            s = b + s[len(a):]
            break
    return s


def clean_filename_piece(s, limit=120):
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r'[<>:"/\\|?*]+', ' ', s)
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+", " ", s).strip(" .-")
    if len(s) > limit:
        s = s[:limit].rstrip(" .-")
    return s or "Untitled"


def parse_context(a):
    ctx = " ".join(a.parent.stripped_strings) if a.parent else " ".join(a.stripped_strings)
    ctx = re.sub(r"\s+", " ", ctx).strip()
    m = re.search(rf'{JOURNAL_NAMES}\s+(\d+)\.(\d+)\s*\(([^)]+)\)\s*:\s*([^\.]+)', ctx, re.I)
    if not m:
        m = re.search(rf'{JOURNAL_NAMES}\s+(\d+)\.(\d+)\s*\(([^)]+)\)\s*:\s*([^\s]+)', ctx, re.I)
    if not m:
        return None
    vol, issue = int(m.group(1)), int(m.group(2))
    date = normalize_month_date(m.group(3))
    pages = m.group(4).strip().replace(" ", "")
    # Remove DOI/pdf tail if page capture was broad.
    pages = re.sub(r'(?i)(https?://.*|pdf.*)$', '', pages).strip(' ,.;')
    if not re.match(r'^\d+(?:[-–]\d+)?$', pages):
        pm = re.search(r'\):\s*(\d+(?:[-–]\d+)?)', ctx)
        pages = pm.group(1) if pm else ""
    title = ""
    journal_m = re.search(rf',\s*{JOURNAL_NAMES}\s+\d+\.\d+', ctx, re.I)
    if journal_m:
        pre = ctx[:journal_m.start()].strip()
        tm = re.match(r'(?s).*?\s*,\s*["“](.*)["”]\s*$', pre)
        if tm:
            title = tm.group(1).strip()
    if not title:
        raw = unquote(a.get("href", "")).split("/")[-1].rsplit(".", 1)[0]
        title = raw.replace("+", " ")
    return vol, issue, date, pages, title, ctx


def main():
    page, diagnostics = discover_page()
    (OUT / "discovery.txt").write_text("page=" + str(page) + "\n" + "\n".join(map(str, diagnostics)), encoding="utf-8")
    if not page:
        print("NO_PAGE_DISCOVERED")
        return 2

    r = get(page)
    (OUT / "source_page.html").write_text(r.text, encoding="utf-8")
    soup = BeautifulSoup(r.text, "html.parser")

    rows = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(page, a["href"])
        if ".pdf" not in href.lower() or href in seen:
            continue
        seen.add(href)
        meta = parse_context(a)
        if meta:
            rows.append((href, *meta))
        else:
            ctx = " ".join(a.parent.stripped_strings) if a.parent else " ".join(a.stripped_strings)
            rows.append((href, None, None, "", "", "", ctx))

    if not rows:
        print("NO_PDFS page=", page)
        return 3

    manifest = []
    for href, vol, issue, date, pages, title, ctx in rows:
        if not (vol and issue and date):
            manifest.append(["", "", "", "", title, href, "", 0, "", "METADATA_UNRESOLVED", ctx[:700]])
            continue
        issue_dir = OUT / f"volume-{vol:03d}" / f"issue-{issue:02d}"
        issue_dir.mkdir(parents=True, exist_ok=True)
        page_part = f" - pp {pages}" if pages else ""
        safe_title = clean_filename_piece(title)
        name = f"African Christian Theology - Volume {vol:03d} - Issue {issue:02d} - {date}{page_part} - {safe_title}.pdf"
        # Keep filename below common 255-byte-ish limits.
        if len(name) > 230:
            over = len(name) - 230
            safe_title = clean_filename_piece(safe_title, max(40, len(safe_title) - over))
            name = f"African Christian Theology - Volume {vol:03d} - Issue {issue:02d} - {date}{page_part} - {safe_title}.pdf"
        dest = issue_dir / name
        try:
            rr = get(href, stream=True)
            h = hashlib.sha256(); n = 0
            with open(dest, "wb") as f:
                for chunk in rr.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk); h.update(chunk); n += len(chunk)
            with open(dest, "rb") as f:
                head = f.read(5)
            if head != b"%PDF-":
                dest.unlink(missing_ok=True)
                raise RuntimeError(f"not PDF magic: {head!r}")
            manifest.append([vol, issue, date, pages, title, href, str(dest.relative_to(OUT)), n, h.hexdigest(), "OK", ctx[:700]])
            print("OK", vol, issue, date, n, name)
        except Exception as e:
            manifest.append([vol, issue, date, pages, title, href, str(dest.relative_to(OUT)), 0, "", "ERROR:" + repr(e), ctx[:700]])
            print("ERROR", href, repr(e))

    with open(OUT / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["volume", "issue", "date", "pages", "title", "source_url", "filename", "bytes", "sha256", "status", "context"])
        w.writerows(manifest)

    ok = sum(1 for r in manifest if r[9] == "OK")
    unresolved = sum(1 for r in manifest if r[9] == "METADATA_UNRESOLVED")
    errors = sum(1 for r in manifest if str(r[9]).startswith("ERROR:"))
    print("PAGE", page, "PDF_LINKS", len(rows), "OK", ok, "UNRESOLVED", unresolved, "ERRORS", errors)
    return 0 if ok and not unresolved and not errors else 4

if __name__ == "__main__":
    sys.exit(main())
