"""Streaming snapshot/delta detection for official XML Spreadsheet 2003 procurement exports.
Snapshots track publication IDs and public fields, not the source XLS. The first run
creates a baseline without issuing historical alerts. No Monday integration here.
"""
import gzip,hashlib,json,zipfile
from decimal import Decimal, InvalidOperation
from datetime import datetime,timedelta,timezone
from pathlib import Path
from lxml.etree import iterparse

NS="{urn:schemas-microsoft-com:office:spreadsheet}"
SNAPSHOTS=Path("state/procurement_snapshots")
MAX_EVENTS=10000
SNAPSHOT_SCHEMA=2
def norm(s):
 return " ".join(str(s or "").split())
def row_values(element):
 result=[];at=0
 for cell in element:
  if cell.tag.rsplit("}",1)[-1]!="Cell":continue
  idx=cell.attrib.get(NS+"Index")
  if idx and idx.isdigit():at=int(idx)-1
  while len(result)<at:result.append("")
  val=next((x.text or "" for x in cell if x.tag.rsplit("}",1)[-1]=="Data"),"")
  if len(result)==at:result.append(norm(val))
  elif len(result)>at:result[at]=norm(val)
  at+=1
 return result
def load_snapshot(kind):
 path=SNAPSHOTS/(kind+".json.gz")
 if not path.exists():return None
 with gzip.open(path,"rt",encoding="utf-8") as file:
  d=json.load(file)
 if d.get("schema") not in (1,SNAPSHOT_SCHEMA) or not isinstance(d.get("items"),dict):
  raise ValueError("Incompatible snapshot "+str(path))
 return d
def get_records(archive):
 with zipfile.ZipFile(archive) as z:
  members=[x for x in z.infolist() if x.filename.lower().endswith(".xls")]
  if len(members)!=1:raise ValueError("Expected exactly one XML spreadsheet")
  with z.open(members[0]) as f:
   header=None
   for event,element in iterparse(f,events=("end",),recover=True,huge_tree=True,encoding="utf-8"):
    tag=element.tag.rsplit("}",1)[-1]
    if tag=="Row":
     cells=row_values(element)
     if header is None:
      header=cells
      if "מספר פרסום" not in header or "סטטוס" not in header:raise ValueError("Unexpected spreadsheet header")
     else:
      if any(cells):yield dict(zip(header,cells))
     element.clear()
     while element.getprevious() is not None:del element.getparent()[0]
def parse_date(d):
 try:return datetime.strptime(norm(d)[:10],"%d.%m.%Y").date()
 except ValueError:return None
def canonical_date(value):
 d=parse_date(value)
 return d.isoformat() if d else norm(value)

def canonical_amount(value):
 s=norm(value).replace(" ","").replace(",","").replace("₪","")
 if not s:return ""
 try:
  dec=format(Decimal(s),"f")
  return dec.rstrip("0").rstrip(".") if "." in dec else dec
 except InvalidOperation:return norm(value)

def financial_summary(rows):
 amounts=sorted({(r[1]+" "+r[2]).strip() for r in rows if r[1]})
 periods=sorted({r[3]+" → "+r[4] for r in rows if r[3] or r[4]})
 return {"amounts":amounts[:15],"amount_values":len(amounts),
         "periods":periods[:15],"period_values":len(periods)}

def index_archive(path,kind):
 groups={};nrows=0;missing_id=0
 for row in get_records(path):
  nrows+=1
  pub=norm(row.get("מספר פרסום"))
  if not pub:
   missing_id+=1
   continue
  entry=groups.get(pub)
  if entry is None:
   entry={"key":pub,"rows":0,"xor":0,"statuses":set(),"winners":set(),
          "financial":[],
          "title":norm(row.get("שם הליך"))[:180],"published":norm(row.get("תאריך פרסום")),
          "updated":norm(row.get("תאריך עדכון")),"agency":norm(row.get("שם המשרד"))[:100]}
   groups[pub]=entry
  entry["rows"]+=1
  entry["statuses"].add(norm(row.get("סטטוס")))
  sup=norm(row.get("שם ספק זוכה" if kind=="tenders" else "שם ספק"))
  hp=norm(row.get("מספר חפ ספק"))
  if sup or hp:entry["winners"].add((hp or "")+"|"+sup)
  amount=canonical_amount(row.get("היקף כספי"))
  currency=norm(row.get("מטבע")).upper()
  start=canonical_date(row.get("תאריך תחילת תקופת התקשרות"))
  end=canonical_date(row.get("תאריך סיום תקופת התקשרות"))
  if amount or currency or start or end:
   entry["financial"].append([hp or sup,amount,currency,start,end])
  # Ignore update timestamp to avoid false positives from metadata-only date changes.
  comparison={k:v for k,v in row.items() if k!="תאריך עדכון"}
  fingerprint=hashlib.sha256(json.dumps(comparison,ensure_ascii=False,sort_keys=True).encode()).digest()
  entry["xor"]^=int.from_bytes(fingerprint,"big")
 if not nrows or not groups or missing_id>nrows*.02:
  raise ValueError(f"Invalid source: rows={nrows}, keys={len(groups)}, missing={missing_id}")
 items={}
 for key,e in groups.items():
  items[key]={"digest":format(e["xor"],"064x"),"rows":e["rows"],
    "statuses":sorted(e["statuses"]),"winners":sorted(e["winners"]),
    "title":e["title"],"published":e["published"],"updated":e["updated"],
    "agency":e["agency"],"financial":sorted(e["financial"])}
 return {"schema":SNAPSHOT_SCHEMA,"kind":kind,"rows":nrows,"missing_ids":missing_id,"items":items}
def compare(old,new):
 if old is None:
  return {"status":"baseline","old_records":0,"new_records":new["rows"],
          "old_publications":0,"new_publications":len(new["items"]),"counts":{},"recent_counts":{},
          "events":[],"omitted_events":0}
 prior=old["items"];current=new["items"]
 if len(current)<len(prior)*.75:
  raise ValueError("Publication count dropped >25%; refusing destructive replacement")
 counts={"new_publication":0,"winner_assigned":0,"winner_changed":0,"status_changed":0,"details_changed":0,"removed":0}
 recent={k:0 for k in counts};events=[]
 cutoff=datetime.now(timezone.utc).date()-timedelta(days=120)
 for key,entry in current.items():
  previous=prior.get(key)
  if previous is None:types=["new_publication"]
  elif previous["digest"]==entry["digest"] and previous["rows"]==entry["rows"]:continue
  else:
   types=[]
   if set(entry["winners"])!=set(previous["winners"]):
    types.append("winner_assigned" if not previous["winners"] and entry["winners"] else "winner_changed")
   if entry["statuses"]!=previous["statuses"]:types.append("status_changed")
   if not types:types.append("details_changed")
  date=parse_date(entry["published"]);is_recent=bool(date and date>=cutoff)
  for change in types:
   counts[change]+=1
   if is_recent:recent[change]+=1
  if len(events)<MAX_EVENTS and is_recent and "details_changed" not in types:
   events.append({"event_id":hashlib.sha256((new["kind"]+":"+key+":"+entry["digest"]).encode()).hexdigest()[:20],
    "publication_id":key,"change_types":types,"published":entry["published"],"updated":entry["updated"],
    "title":entry["title"],"agency":entry["agency"],"statuses":entry["statuses"],
    "winners":entry["winners"][:10]})
 for key in prior.keys()-current.keys():counts["removed"]+=1
 return {"status":"compared","old_records":old["rows"],"new_records":new["rows"],
         "old_publications":len(prior),"new_publications":len(current),
         "counts":counts,"recent_counts":recent,"events":events,
         "omitted_events":max(0,sum(recent.values())-len(events)),
         "recent_definition":"publication date within 120 days, not necessarily first observed"}
def prepare(path,kind,dest):
 old=load_snapshot(kind)
 new=index_archive(path,kind)
 result=compare(old,new)
 dest.parent.mkdir(parents=True,exist_ok=True)
 with gzip.open(dest,"wt",encoding="utf-8",compresslevel=6) as f:
  json.dump(new,f,ensure_ascii=False,separators=(",",":"))
 return result
