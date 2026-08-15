import csv, hashlib, os, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASES = [
    "https://biblicalstudies.gospelstudies.org.uk/",
    "https://www.biblicalstudies.org.uk/",
]
OUT = Path("out_african_christian_theology")
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 BSUK-Drive-Archiver/0.2"}


def get(url, stream=False):
    r = requests.get(url, headers=UA, timeout=60, stream=stream, allow_redirects=True)
    r.raise_for_status()
    return r


def discover_page():
    diagnostics=[]
    for base in BASES:
        for entry in ("articles.php", "sitemap.php"):
            url=urljoin(base, entry)
            try:
                r=get(url)
                text=r.text
                soup=BeautifulSoup(text, "html.parser")
                # Prefer select option / anchor explicitly naming the journal.
                for tag in soup.find_all(["option","a"]):
                    label=" ".join(tag.stripped_strings)
                    if "African Christian Theology" in label:
                        href=tag.get("value") if tag.name=="option" else tag.get("href")
                        diagnostics.append((url, tag.name, label, href or ""))
                        if href and href not in ("#", ""):
                            candidate=urljoin(url, href)
                            if "afric" in candidate.lower() or "christian" in candidate.lower() or "articles_" in candidate.lower():
                                return candidate, diagnostics
                # Capture nearby href/value in raw HTML as fallback.
                m=re.search(r'(?is)(?:href|value)=["\']([^"\']+)["\'][^>]{0,300}>?[^<]{0,120}African Christian Theology', text)
                if m:
                    return urljoin(url,m.group(1)), diagnostics
                m=re.search(r'(?is)African Christian Theology.{0,400}?(?:href|value)=["\']([^"\']+)["\']', text)
                if m:
                    return urljoin(url,m.group(1)), diagnostics
            except Exception as e:
                diagnostics.append((url,"ERROR",repr(e),""))
    return None, diagnostics


def issue_metadata_from_context(a):
    txt=" ".join(a.parent.stripped_strings) if a.parent else a.get_text(" ",strip=True)
    txt=re.sub(r"\s+"," ",txt)
    # Prefer citation-like Volume.Issue (Year)
    m=re.search(r'(?:African Christian Theology\s+)?(\d+)\.(\d+)\s*\((20\d{2})\)', txt, re.I)
    if not m:
        m=re.search(r'\b(\d+)\.(\d+)\b.*?\b(20\d{2})\b', txt)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3)), txt
    # Headings sometimes place year separately; inspect previous headings/siblings.
    scope=a
    context=[]
    for _ in range(8):
        scope=scope.previous_element if scope else None
        if scope is None: break
        s=str(scope).strip()
        if s: context.append(s)
    blob=" ".join(reversed(context))+" "+txt
    m=re.search(r'Vol\.\s*(\d+).*?\((20\d{2})\)', blob, re.I)
    im=re.search(r'\b(\d+)\.(\d+)\b', txt)
    if m and im:
        return int(im.group(1)), int(im.group(2)), int(m.group(2)), txt
    return None,None,None,txt


def main():
    page, diagnostics=discover_page()
    (OUT/"discovery.txt").write_text("page="+str(page)+"\n"+"\n".join(map(str,diagnostics)),encoding="utf-8")
    if not page:
        print("NO_PAGE_DISCOVERED")
        return 2
    r=get(page)
    (OUT/"source_page.html").write_text(r.text,encoding="utf-8")
    soup=BeautifulSoup(r.text,"html.parser")
    candidates=[]
    for a in soup.find_all("a", href=True):
        href=urljoin(page,a["href"])
        label=" ".join(a.stripped_strings)
        surrounding=" ".join(a.parent.stripped_strings) if a.parent else label
        if ".pdf" not in href.lower():
            continue
        # Archive complete issues only; do not archive individual articles.
        if "complete issue" not in (label+" "+surrounding).lower():
            continue
        vol,issue,year,ctx=issue_metadata_from_context(a)
        candidates.append((href,label,vol,issue,year,ctx))
    # de-duplicate hrefs
    uniq=[]; seen=set()
    for row in candidates:
        if row[0] not in seen:
            seen.add(row[0]); uniq.append(row)
    candidates=uniq
    if not candidates:
        print("NO_COMPLETE_ISSUE_PDFS page=",page)
        return 3
    manifest=[]
    for href,label,vol,issue,year,ctx in candidates:
        if not (vol and issue and year):
            manifest.append([vol or "",issue or "",year or "",href,"",0,"","METADATA_UNRESOLVED",ctx[:500]])
            continue
        dest=OUT/f"African Christian Theology - Volume {vol:03d} - Issue {issue:02d} - {year}.pdf"
        try:
            rr=get(href,stream=True)
            h=hashlib.sha256(); n=0
            with open(dest,"wb") as f:
                for chunk in rr.iter_content(1024*1024):
                    if chunk:
                        f.write(chunk); h.update(chunk); n+=len(chunk)
            with open(dest,"rb") as f:
                head=f.read(5)
            if head!=b"%PDF-":
                dest.unlink(missing_ok=True)
                raise RuntimeError(f"not PDF magic: {head!r}")
            manifest.append([vol,issue,year,href,str(dest.name),n,h.hexdigest(),"OK",ctx[:500]])
            print("OK",vol,issue,year,n)
        except Exception as e:
            manifest.append([vol,issue,year,href,str(dest.name),0,"","ERROR:"+repr(e),ctx[:500]])
    with open(OUT/"manifest.csv","w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["volume","issue","year","source_url","filename","bytes","sha256","status","context"]); w.writerows(manifest)
    ok=sum(1 for r in manifest if r[7]=="OK")
    print("PAGE",page,"CANDIDATES",len(candidates),"OK",ok)
    return 0 if ok else 4

if __name__=="__main__":
    sys.exit(main())
