#!/usr/bin/env python3
import io, os, re, json, time, hashlib, tempfile, subprocess, unicodedata
from pathlib import Path
from collections import defaultdict, deque

import fitz
from rapidfuzz import fuzz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

SCOPES=["https://www.googleapis.com/auth/drive","https://www.googleapis.com/auth/spreadsheets"]
SOURCE_NAME=os.getenv("SOURCE_NAME","للفحص")
ENGLISH_NAME=os.getenv("ENGLISH_LIBRARY_NAME","المكتبة الإنجليزية")
ARABIC_NAME=os.getenv("ARABIC_LIBRARY_NAME","المكتبة العربية")
SYSTEM_NAME=os.getenv("SYSTEM_FOLDER_NAME","00 - نظام إدارة الفحص والجرد")
TARGET=max(50,int(os.getenv("BATCH_TARGET","60")))
MIN_BATCH=max(10,int(os.getenv("MIN_MICROBATCH","10")))
MAX_DOWNLOAD_MB=int(os.getenv("MAX_DOWNLOAD_MB","180"))
STATE_NAME="library-processor-state.json"
AUDIT_NAME="library-processor-audit.jsonl"
INDEX_NAME="library-processor-index.json"
PDF="application/pdf"
FOLDER="application/vnd.google-apps.folder"

class StopFree(Exception): pass

def creds():
    raw=os.environ.get("GDRIVE_OAUTH_JSON","").strip()
    if not raw: raise SystemExit("Missing GDRIVE_OAUTH_JSON secret")
    cfg=json.loads(raw)
    c=Credentials(token=None,refresh_token=cfg["refresh_token"],token_uri="https://oauth2.googleapis.com/token",client_id=cfg["client_id"],client_secret=cfg["client_secret"],scopes=SCOPES)
    c.refresh(Request())
    return c

C=creds(); D=build("drive","v3",credentials=C,cache_discovery=False)

def api(call):
    delay=1
    for n in range(6):
        try: return call.execute()
        except HttpError as e:
            code=getattr(e.resp,"status",0)
            txt=str(e)
            if code in (403,429) and any(x in txt for x in ["dailyLimitExceeded","userRateLimitExceeded","rateLimitExceeded","quota"]):
                if n>=4: raise StopFree("Drive quota/rate guard triggered; stopped rather than escalating quota or cost")
                time.sleep(delay); delay=min(delay*2,20); continue
            if code>=500 and n<5: time.sleep(delay); delay=min(delay*2,20); continue
            raise

def listq(q,fields="nextPageToken,files(id,name,mimeType,parents,md5Checksum,size,modifiedTime,createdTime,trashed)"):
    out=[]; token=None
    while True:
        r=api(D.files().list(q=q,spaces="drive",pageSize=1000,pageToken=token,fields=fields,includeItemsFromAllDrives=True,supportsAllDrives=True))
        out+=r.get("files",[]); token=r.get("nextPageToken")
        if not token: return out

def exact_folder(name):
    esc=name.replace("'","\\'")
    hits=listq(f"name = '{esc}' and mimeType = '{FOLDER}' and trashed = false")
    if len(hits)!=1: raise SystemExit(f"Expected exactly one folder named {name!r}, found {len(hits)}")
    return hits[0]

def children(fid): return listq(f"'{fid}' in parents and trashed = false")

def scan_tree(root_id):
    folders={root_id}; files=[]; q=deque([root_id])
    while q:
        p=q.popleft()
        for x in children(p):
            if x["mimeType"]==FOLDER: folders.add(x["id"]); q.append(x["id"])
            else: files.append(x)
    return folders,files

def norm(s):
    s=unicodedata.normalize("NFKC",s or "").lower()
    s=re.sub(r"\.pdf$","",s)
    s=re.sub(r"[^0-9a-z\u0600-\u06ff]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def stem_for_sort(s):
    s=re.sub(r"\.pdf$","",s,flags=re.I).strip()
    s=re.sub(r"^(a|an|the)\s+","",s,flags=re.I)
    return s.strip(" _-–—:;,.()[]{}")

def arabic_ratio(s):
    letters=re.findall(r"[A-Za-z\u0600-\u06ff]",s or "")
    if not letters:return 0.0
    return sum(1 for c in letters if "\u0600"<=c<="\u06ff")/len(letters)

def download(fid,path):
    req=D.files().get_media(fileId=fid,supportsAllDrives=True)
    with open(path,"wb") as fh:
        dl=MediaIoBaseDownload(fh,req,chunksize=8*1024*1024)
        done=False
        while not done: _,done=dl.next_chunk()

def pdf_text(path,max_pages=8):
    doc=fitz.open(path); parts=[]
    for i in range(min(max_pages,len(doc))):
        try: parts.append(doc[i].get_text("text"))
        except: pass
    text="\n".join(parts)
    return text,len(doc)

def ocr_first(path,pages=4):
    out=[]
    with tempfile.TemporaryDirectory() as td:
        pref=str(Path(td)/"p")
        subprocess.run(["pdftoppm","-f","1","-l",str(pages),"-jpeg","-r","150",path,pref],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        for img in sorted(Path(td).glob("p-*.jpg")):
            p=subprocess.run(["tesseract",str(img),"stdout","-l","eng+ara","--psm","6"],capture_output=True,text=True)
            if p.stdout: out.append(p.stdout)
    return "\n".join(out)

def metadata_from_text(text,filename,pages):
    clean=[re.sub(r"\s+"," ",x).strip() for x in text.splitlines()]
    clean=[x for x in clean if 3<=len(x)<=180]
    bad=re.compile(r"^(page|chapter|contents|copyright|isbn|www\.|http|طبعة|الطبعة|الفهرس|المحتويات)\b",re.I)
    candidates=[x for x in clean[:80] if not bad.search(x)]
    title=candidates[0] if candidates else re.sub(r"\.pdf$","",filename,flags=re.I)
    title=re.sub(r"^[\d\s._-]+(?=[A-Za-z\u0600-\u06ff])","",title).strip()
    author=""
    for x in clean[:120]:
        m=re.search(r"\b(?:by|author)\s*[:\-]?\s*(.{3,90})$",x,re.I)
        if m: author=m.group(1).strip(); break
        m=re.search(r"(?:تأليف|المؤلف|بقلم|إعداد)\s*[:\-]?\s*(.{3,90})$",x)
        if m: author=m.group(1).strip(); break
    edition=""
    for x in clean[:160]:
        m=re.search(r"\b((?:first|second|third|fourth|fifth|\d+(?:st|nd|rd|th))\s+edition)\b",x,re.I)
        if m: edition=m.group(1); break
        m=re.search(r"(?:الطبعة|طبعة)\s+([^,.;]{1,40})",x)
        if m: edition="الطبعة "+m.group(1).strip(); break
    years=re.findall(r"(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)","\n".join(clean[:200]))
    year=years[-1] if years else ""
    return {"title":title[:180],"author":author[:120],"edition":edition[:60],"year":year,"pages":pages}

def safe_name(meta,old):
    title=meta.get("title") or re.sub(r"\.pdf$","",old,flags=re.I)
    parts=[title]
    if meta.get("author"): parts.append(meta["author"])
    if meta.get("edition"): parts.append(meta["edition"])
    elif meta.get("year"): parts.append(meta["year"])
    name=" - ".join(p.strip(" -–—") for p in parts if p.strip())
    name=re.sub(r"[\\/:*?\"<>|]"," - ",name)
    name=re.sub(r"\s+"," ",name).strip(" .-")[:220]
    return (name or re.sub(r"\.pdf$","",old,flags=re.I))+".pdf"

def title_key(meta,filename): return norm(meta.get("title") or filename)

def candidate_score(src_meta,src_name,lib):
    a=title_key(src_meta,src_name); b=norm(lib["name"])
    return fuzz.token_set_ratio(a,b)

def read_candidate_text(fid):
    with tempfile.TemporaryDirectory() as td:
        p=str(Path(td)/"c.pdf"); download(fid,p)
        t,_=pdf_text(p,5)
        if len(t.strip())<300: t+="\n"+ocr_first(p,3)
        return norm(t[:12000])

def choose_letter_folder(root_id,title,arabic):
    fs=[x for x in children(root_id) if x["mimeType"]==FOLDER]
    by={unicodedata.normalize("NFKC",x["name"]).strip().lower():x["id"] for x in fs}
    s=stem_for_sort(title)
    if not s:return root_id
    if arabic:
        s=re.sub(r"^[^\u0621-\u064a]+","",s)
        ch=s[0] if s else ""
        # normalize Arabic letter variants to common filing letters
        ch={"أ":"ا","إ":"ا","آ":"ا","ى":"ي","ة":"ه","ؤ":"و","ئ":"ي"}.get(ch,ch)
        return by.get(ch,root_id)
    s=re.sub(r"^[^A-Za-z]+","",s)
    return by.get(s[:1].lower(),root_id) if s else root_id

def drive_json_file(folder_id,name):
    esc=name.replace("'","\\'")
    h=listq(f"'{folder_id}' in parents and name = '{esc}' and trashed = false")
    return h[0] if h else None

def load_small_json(folder_id,name,default):
    f=drive_json_file(folder_id,name)
    if not f:return default
    bio=io.BytesIO(); dl=MediaIoBaseDownload(bio,D.files().get_media(fileId=f["id"])); done=False
    while not done: _,done=dl.next_chunk()
    try:return json.loads(bio.getvalue().decode("utf-8"))
    except:return default

def save_bytes(folder_id,name,data,mime="application/json"):
    f=drive_json_file(folder_id,name); media=MediaIoBaseUpload(io.BytesIO(data),mimetype=mime,resumable=False)
    if f: api(D.files().update(fileId=f["id"],media_body=media,supportsAllDrives=True))
    else: api(D.files().create(body={"name":name,"parents":[folder_id]},media_body=media,fields="id",supportsAllDrives=True))

def append_audit(folder_id,rows):
    if not rows:return
    old=b""; f=drive_json_file(folder_id,AUDIT_NAME)
    if f:
        bio=io.BytesIO(); dl=MediaIoBaseDownload(bio,D.files().get_media(fileId=f["id"])); done=False
        while not done: _,done=dl.next_chunk()
        old=bio.getvalue()
    new=old+b"".join((json.dumps(r,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8") for r in rows)
    save_bytes(folder_id,AUDIT_NAME,new,"application/x-ndjson")

def move_and_rename(file,dest,new_name):
    parents=file.get("parents",[])
    body={"name":new_name}
    kwargs={"fileId":file["id"],"body":body,"addParents":dest,"fields":"id,name,parents","supportsAllDrives":True}
    if parents: kwargs["removeParents"]=",".join(parents)
    return api(D.files().update(**kwargs))

def main():
    source=exact_folder(SOURCE_NAME); eng=exact_folder(ENGLISH_NAME); ara=exact_folder(ARABIC_NAME); system=exact_folder(SYSTEM_NAME)
    _,eng_files=scan_tree(eng["id"]); _,ara_files=scan_tree(ara["id"]); _,src_files=scan_tree(source["id"])
    libraries=eng_files+ara_files
    md5=defaultdict(list)
    for x in libraries:
        if x.get("md5Checksum"): md5[x["md5Checksum"]].append(x)
    state=load_small_json(system["id"],STATE_NAME,{"processed":{},"runs":0})
    done_ids=set(state.get("processed",{}))
    candidates=[x for x in src_files if x["id"] not in done_ids and x["mimeType"]==PDF]
    candidates.sort(key=lambda x:x.get("createdTime",x.get("modifiedTime","")))
    work=candidates[:TARGET]
    audit=[]; processed=0; moved=0; dup=0; review=0
    for file in work:
        rec={"ts":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"file_id":file["id"],"original_name":file["name"]}
        try:
            if file.get("md5Checksum") and md5.get(file["md5Checksum"]):
                rec.update(status="DUPLICATE_CONFIRMED",evidence="same Drive md5Checksum",duplicate_ids=[x["id"] for x in md5[file["md5Checksum"]][:5]])
                dup+=1; processed+=1; state["processed"][file["id"]]=rec["status"]; audit.append(rec); continue
            size=int(file.get("size") or 0)
            if size>MAX_DOWNLOAD_MB*1024*1024:
                rec.update(status="REVIEW_REQUIRED",reason=f"file larger than safe per-file download cap {MAX_DOWNLOAD_MB} MB")
                review+=1; processed+=1; state["processed"][file["id"]]=rec["status"]; audit.append(rec); continue
            with tempfile.TemporaryDirectory() as td:
                p=str(Path(td)/"s.pdf"); download(file["id"],p)
                text,pages=pdf_text(p,8)
                if len(text.strip())<500: text+="\n"+ocr_first(p,4)
                meta=metadata_from_text(text,file["name"],pages); rec["meta"]=meta
                ar=arabic_ratio((meta.get("title","")+" "+text[:4000]))>=0.35
                rec["language"]="ar" if ar else "en"
                scored=sorted(((candidate_score(meta,file["name"],x),x) for x in libraries),key=lambda z:z[0],reverse=True)[:6]
                suspicious=[(s,x) for s,x in scored if s>=88]
                exact_work=False; relation=""
                src_probe=norm(text[:12000])
                for s,x in suspicious[:3]:
                    try: cand=read_candidate_text(x["id"])
                    except Exception: cand=""
                    sim=fuzz.token_set_ratio(src_probe,cand) if cand else s
                    if sim>=97:
                        exact_work=True; relation="PROBABLE_DUPLICATE"; rec["duplicate_candidate"]={"id":x["id"],"name":x["name"],"score":sim}; break
                    if sim>=90: relation="SAME_WORK_DIFFERENT_EDITION"
                if exact_work:
                    rec["status"]="PROBABLE_DUPLICATE"; dup+=1
                else:
                    new=safe_name(meta,file["name"])
                    root=ara["id"] if ar else eng["id"]
                    dest=choose_letter_folder(root,meta.get("title") or new,ar)
                    result=move_and_rename(file,dest,new)
                    if result.get("id")!=file["id"] or dest not in result.get("parents",[]): raise RuntimeError("post-move QA failed")
                    rec.update(status=relation or "NOT_DUPLICATE",action="RENAMED_AND_MOVED",canonical_name=result["name"],destination_id=dest)
                    moved+=1; libraries.append({**file,"name":result["name"],"parents":[dest]})
                    if file.get("md5Checksum"): md5[file["md5Checksum"]].append(file)
                processed+=1; state["processed"][file["id"]]=rec["status"]
                audit.append(rec)
        except StopFree: raise
        except Exception as e:
            rec.update(status="REVIEW_REQUIRED",reason=str(e)[:500]); review+=1; processed+=1; state["processed"][file["id"]]=rec["status"]; audit.append(rec)
        if len(audit)>=MIN_BATCH:
            append_audit(system["id"],audit); audit=[]
            state.update(last_run=time.time(),last_counts={"processed":processed,"moved":moved,"duplicates":dup,"review":review})
            save_bytes(system["id"],STATE_NAME,json.dumps(state,ensure_ascii=False).encode("utf-8"))
    append_audit(system["id"],audit)
    state["runs"]=int(state.get("runs",0))+1
    state.update(last_run=time.time(),last_counts={"processed":processed,"moved":moved,"duplicates":dup,"review":review},remaining=max(0,len(candidates)-len(work)))
    save_bytes(system["id"],STATE_NAME,json.dumps(state,ensure_ascii=False).encode("utf-8"))
    # privacy-preserving index summary only; no filenames or IDs in GitHub logs
    idx={"generated":state["last_run"],"english_files":len(eng_files),"arabic_files":len(ara_files),"source_candidates":len(candidates)}
    save_bytes(system["id"],INDEX_NAME,json.dumps(idx).encode("utf-8"))
    print(json.dumps({"processed":processed,"moved":moved,"duplicates":dup,"review":review,"remaining":state["remaining"]}))
    if processed<50 and len(candidates)>=50:
        raise SystemExit("Throughput floor not met: run marked failed so scheduler retries on next cycle")

if __name__=="__main__":
    try: main()
    except StopFree as e:
        print(str(e)); raise SystemExit(75)
