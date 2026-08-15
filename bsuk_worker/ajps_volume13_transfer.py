from pathlib import Path
import hashlib
import requests

URL = "https://biblicalstudies.gospelstudies.org.uk/pdf/ajps/ajps-13-1_003.pdf"
OUT = Path("out_ajps13/ajps-13-1_003.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)

r = requests.get(URL, timeout=90, headers={"User-Agent": "Mozilla/5.0 BSUK-Drive-Archiver/0.1"})
r.raise_for_status()
data = r.content
if not data.startswith(b"%PDF-"):
    raise RuntimeError(f"Not a PDF: status={r.status_code} content-type={r.headers.get('content-type')} bytes={len(data)}")
OUT.write_bytes(data)
print(f"OK {OUT} bytes={len(data)} sha256={hashlib.sha256(data).hexdigest()}")
