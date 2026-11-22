"""Public daily tracker of official government monthly procurement exports.
Compares exact page-published ZIP URLs; stores public version metadata, never XLS.
"""
import argparse,hashlib,html,json,re,sys,tempfile,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request,urlopen
from procurement_delta import SNAPSHOTS, prepare
PAGE="https://mr.gov.il/ilgstorefront/he/news/details/230920201036"
STATE=Path("state/procurement_versions.json")
REPORT=Path("procurement_daily_report.json")
KINDS=("tenders","exemptions")
def now():return datetime.now(timezone.utc).isoformat()
def req(url,t=35):return urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; RosarioPublicFeeds/1.0)","Accept":"text/html,application/zip,*/*"}),timeout=t)
def extract(page):
 page=html.unescape(page).replace("\/","/").replace("\u0026","&")
 matches=re.findall(r'(?:https?://(?:www\.)?mr\.gov\.il)?/ilgstorefront/medias/(?:Tenders|Exemptions)-\d{8}\.zip(?:\?context=[A-Za-z0-9_%+=/-]+)?',page,re.I)
 out={}
 for raw in matches:
  u=urljoin(PAGE,raw) if raw.startswith("/") else raw
  kind="tenders" if "/Tenders-" in u else "exemptions"
  ds=re.search(r'-(\d{8})\.zip',u)
  if not ds:continue
  try:d=datetime.strptime(ds.group(1),"%d%m%Y").date()
  except ValueError:continue
  rank=(d,"context=" in u)
  if kind not in out or rank>out[kind][0]:out[kind]=(rank,u)
 return {k:v[1] for k,v in out.items()}
def listing():
 with req(PAGE) as r:
  data=r.read(5_000_000)
  if r.status!=200 or not data:raise RuntimeError("listing unavailable")
  return {"bytes":len(data),"links":extract(data.decode("utf-8","replace"))}
def verify(url,kind):
 with tempfile.TemporaryDirectory() as td:
  path=Path(td)/(kind+".zip");size=0;digest=hashlib.sha256()
  with req(url,75) as r,path.open("wb") as f:
   if r.status!=200:raise RuntimeError("ZIP HTTP "+str(r.status))
   while True:
    b=r.read(524288)
    if not b:break
    size+=len(b)
    if size>80000000:raise RuntimeError("ZIP too large")
    f.write(b);digest.update(b)
  if not zipfile.is_zipfile(path):raise RuntimeError("not a ZIP")
  with zipfile.ZipFile(path) as z:
   entries=[{"name":x.filename,"uncompressed_bytes":x.file_size} for x in z.infolist()]
   if not any(x["name"].lower().endswith((".xls",".xlsx",".csv")) for x in entries):raise RuntimeError("no spreadsheet")
   if z.testzip() is not None:raise RuntimeError("ZIP CRC failed")
  pending=SNAPSHOTS/(kind+".json.gz.pending")
  delta=prepare(path,kind,pending)
  return {"bytes":size,"sha256":digest.hexdigest(),"entries":entries,"delta":delta}
def run(force=False):
 previous=json.loads(STATE.read_text("utf-8")) if STATE.exists() else {"versions":{}}
 report={"checked_utc":now(),"source_page":PAGE,"results":{},"outcome":"unknown"}
 try:
  ls=listing();urls=ls["links"]
  report["listing_bytes"]=ls["bytes"];report["detected"]=sorted(urls)
  if set(urls)!=set(KINDS):raise RuntimeError("Missing official links, state unchanged: "+str(list(urls)))
  updated=dict(previous.get("versions",{}))
  for kind in KINDS:
   url=urls[kind];old=updated.get(kind,{})
   if old.get("url")==url and (SNAPSHOTS/(kind+".json.gz")).exists() and not force:
    report["results"][kind]={"status":"unchanged","downloaded_bytes":0,"url":url};continue
   info={"url":url,"status":"new" if url!=old.get("url") else "revalidated"}
   try:
    info.update(verify(url,kind))
    updated[kind]={"url":url,"first_seen_utc":now() if url!=old.get("url") else old.get("first_seen_utc",now()),"sha256":info["sha256"],"bytes":info["bytes"],"entries":info["entries"]}
   except Exception as e:info.update(status="failed",error=f"{type(e).__name__}: {e}")
   report["results"][kind]=info
  if any(x["status"]=="failed" for x in report["results"].values()):raise RuntimeError("ZIP validation failed; state unchanged")
  for kind in KINDS:
   pending=SNAPSHOTS/(kind+".json.gz.pending")
   if pending.exists():pending.replace(SNAPSHOTS/(kind+".json.gz"))
  events={"checked_utc":now(),"kinds":{k:v.get("delta",{"status":"unchanged","counts":{},"recent_counts":{},"events":[]}) for k,v in report["results"].items()}}
  Path("procurement_events.json").write_text(json.dumps(events,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  if updated!=previous.get("versions",{}):
   STATE.parent.mkdir(parents=True,exist_ok=True)
   STATE.write_text(json.dumps({"updated_utc":now(),"versions":updated},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  report["outcome"]="ok"
 except Exception as e:
  report.update(outcome="failed",error=f"{type(e).__name__}: {e}")
  for kind in KINDS:
   pending=SNAPSHOTS/(kind+".json.gz.pending")
   if pending.exists():pending.unlink()
 REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 for k,v in report["results"].items():print(k,v["status"],"downloaded",v.get("bytes",v.get("downloaded_bytes",0)),flush=True)
 print("OUTCOME",report["outcome"],report.get("error",""),flush=True)
 return report
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--force-download",action="store_true")
 sys.exit(0 if run(p.parse_args().force_download)["outcome"]=="ok" else 1)
