import csv
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PAGES = [
    "https://biblicalstudies.gospelstudies.org.uk/articles_anvil_01.php",
    "https://biblicalstudies.gospelstudies.org.uk/articles_anvil_02.php",
    "https://biblicalstudies.gospelstudies.org.uk/articles_anvil_03.php",
]
OUT = Path("out_anvil_repair")
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 BSUK-Drive-Archiver/0.2"}
BROKEN_BASENAME = "16-4_247.pdf"
DROPBOX_ZIP = "https://www.dropbox.com/s/nj9zo8yt8uraz8z/anvil.zip?dl=1"


def get(url, stream=False):
    r = requests.get(url, headers=UA, timeout=120, stream=stream, allow_redirects=True)
    r.raise_for_status()
    return r


def clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("/", "-").replace("\\", "-").replace(":", " -")
    s = re.sub(r'[<>:"/\\|?*]', '', s)
    return s.strip(" .-")


def old_parser_would_fail(label):
    return re.search(r"(?:\bAnvil\s+)?(\d{1,2})\.(\d{1,2})\s*\((\d{4})\)\s*:\s*([0-9]+(?:\s*[-–]\s*[0-9]+)?)", label, re.I) is None


def parse_flexible(label):
    text = re.sub(r"\s+", " ", label).strip()
    # Combined issue form: Anvil 26.3 & 4 (2009): 147-159.
    m = re.search(r"(?:\bAnvil\s+)?(\d{1,2})\.(\d{1,2})\s*&\s*(\d{1,2})\s*\((\d{4})\)", text, re.I)
    combined = False
    if m:
        vol, i1, i2, year = map(int, m.groups())
        issue_token = f"{i1:02d}-{i2:02d}"
        coord_start = m.start()
        coord_end = m.end()
        combined = True
    else:
        m = re.search(r"(?:\bAnvil\s+)?(\d{1,2})[\.:](\d{1,2})\s*\((\d{4})\)", text, re.I)
        if not m:
            return None
        vol, i1, year = map(int, m.groups())
        issue_token = f"{i1:02d}"
        coord_start = m.start()
        coord_end = m.end()
    tail = text[coord_end:]
    page_matches = re.findall(r":\s*\(?\d{4}\)?\s*:\s*([0-9]+(?:\s*[-–]\s*[0-9]+)?)|:\s*([0-9]+(?:\s*[-–]\s*[0-9]+)?)", tail)
    pages = ""
    if page_matches:
        vals=[]
        for a,b in page_matches:
            v=a or b
            if v: vals.append(v)
        if vals:
            pages = re.sub(r"\s+", "", vals[-1]).replace("–", "-")
    lead = text[:coord_start].strip(" ,.-")
    lead = re.sub(r"\bAnvil\s*$", "", lead, flags=re.I).strip(" ,.-")
    return vol, issue_token, year, pages, lead, combined


def filename_and_rel(meta):
    vol, issue_token, year, pages, lead, combined = meta
    issue_label = f"Issues {issue_token}" if combined else f"Issue {issue_token}"
    base = f"Anvil - Volume {vol:03d} - {issue_label} - {year}"
    if pages:
        base += f" - pp {pages}"
    if lead:
        base += " - " + clean(lead)
    base = clean(base)
    if len(base) > 210:
        base = base[:210].rstrip(" .-")
    folder = f"Issues {issue_token}" if combined else f"Issue {issue_token}"
    rel = Path(f"Volume {vol:03d} - {year}") / folder / (base + ".pdf")
    return base + ".pdf", rel


def write_pdf_from_response(url, dest):
    rr=get(url,stream=True); h=hashlib.sha256(); n=0
    dest.parent.mkdir(parents=True,exist_ok=True)
    with open(dest,"wb") as f:
        for chunk in rr.iter_content(1024*1024):
            if chunk:
                f.write(chunk); h.update(chunk); n+=len(chunk)
    with open(dest,"rb") as f: magic=f.read(5)
    if magic!=b"%PDF-":
        dest.unlink(missing_ok=True); raise RuntimeError(f"not PDF magic {magic!r}")
    return n,h.hexdigest()


def recover_from_dropbox(basename, dest):
    print("DROPBOX_FALLBACK", basename)
    r=get(DROPBOX_ZIP)
    z=zipfile.ZipFile(io.BytesIO(r.content))
    candidates=[n for n in z.namelist() if Path(n).name.lower()==basename.lower()]
    if not candidates:
        raise FileNotFoundError(f"{basename} not present in official Anvil zip")
    data=z.read(candidates[0])
    if data[:5]!=b"%PDF-": raise RuntimeError("zip member not PDF")
    dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
    return len(data),hashlib.sha256(data).hexdigest()


def main():
    targets=[]; seen=set()
    for page in PAGES:
        soup=BeautifulSoup(get(page).text,"html.parser")
        for a in soup.find_all("a",href=True):
            href=urljoin(page,a["href"])
            p=urlparse(href)
            if "/pdf/anvil/" not in p.path.lower() or not p.path.lower().endswith(".pdf"): continue
            label=" ".join(a.stripped_strings)
            basename=Path(p.path).name
            if not (old_parser_would_fail(label) or basename.lower()==BROKEN_BASENAME.lower()): continue
            if href in seen: continue
            seen.add(href)
            meta=parse_flexible(label)
            targets.append((page,href,label,basename,meta))
    rows=[]
    print("REPAIR_TARGETS",len(targets))
    for page,href,label,basename,meta in targets:
        if not meta:
            rows.append([page,href,label,"","","",0,"","METADATA_UNRESOLVED"]); continue
        filename,rel=filename_and_rel(meta); dest=OUT/rel
        try:
            try:
                n,sha=write_pdf_from_response(href,dest)
                source_used=href
            except Exception as first:
                alt=href.replace("https://biblicalstudies.gospelstudies.org.uk/","https://www.biblicalstudies.org.uk/")
                try:
                    n,sha=write_pdf_from_response(alt,dest); source_used=alt
                except Exception:
                    if basename.lower()==BROKEN_BASENAME.lower():
                        n,sha=recover_from_dropbox(basename,dest); source_used=DROPBOX_ZIP+"#"+basename
                    else:
                        raise first
            rows.append([page,href,label,filename,str(rel),source_used,n,sha,"OK"])
            print("OK",basename,n,filename)
        except Exception as e:
            rows.append([page,href,label,filename,str(rel),"",0,"","ERROR:"+repr(e)])
            print("ERROR",basename,repr(e))
    with open(OUT/"manifest.csv","w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["source_page","source_url","label","filename","relative_path","source_used","bytes","sha256","status"]); w.writerows(rows)
    ok=sum(1 for r in rows if r[-1]=="OK"); bad=len(rows)-ok
    print("SUMMARY OK",ok,"BAD",bad)
    return 0 if rows and bad==0 else 4

if __name__=="__main__": sys.exit(main())
