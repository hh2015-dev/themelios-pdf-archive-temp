from pathlib import Path
import hashlib
import requests

URLS = [
    "https://biblicalstudies.gospelstudies.org.uk/pdf/abtapl/02-01.pdf",
    "https://www.biblicalstudies.org.uk/pdf/abtapl/02-01.pdf",
]
OUT = Path("bsuk_probe/02-01.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)
headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/pdf,*/*;q=0.8",
}
last = None
for url in URLS:
    try:
        with requests.get(url, headers=headers, stream=True, timeout=90, allow_redirects=True) as r:
            print("GET", url, "->", r.status_code, r.headers.get("content-type"), r.url)
            r.raise_for_status()
            h = hashlib.sha256()
            size = 0
            with OUT.open("wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if chunk:
                        f.write(chunk)
                        h.update(chunk)
                        size += len(chunk)
        sig = OUT.read_bytes()[:5]
        if sig != b"%PDF-":
            raise RuntimeError(f"Not a PDF: signature={sig!r}")
        print("OK", OUT, "bytes=", size, "sha256=", h.hexdigest())
        break
    except Exception as e:
        last = e
        print("FAILED", url, repr(e))
        if OUT.exists():
            OUT.unlink()
else:
    raise SystemExit(f"All sources failed: {last}")
