"""Real full 90-day official RMI scan, read-only; no private Rosario data, no CRM."""
import csv,datetime as dt,json,re,time
from pathlib import Path
from collections import Counter
from zoneinfo import ZoneInfo
import requests

ROOT="https://apps.land.gov.il/MichrazimSite/api"
now=dt.datetime.now(ZoneInfo("Asia/Jerusalem")).date()
since=now-dt.timedelta(days=90)
s=requests.Session();s.headers.update({"User-Agent":"Rosario-public-RMI-full-audit/1.0",
"Origin":"https://apps.land.gov.il","Referer":"https://apps.land.gov.il/MichrazimSite/"})
def api(method,path,**kwargs):
 for i in range(3):
  try:
   r=s.request(method,ROOT+path,timeout=90,**kwargs);r.raise_for_status();return r.json()
  except (requests.RequestException,ValueError):
   if i==2:raise
   time.sleep(2**i)
def date(x):
 try:return dt.date.fromisoformat(str(x)[:10])
 except (ValueError,TypeError):return None
def amount(v):
 try:return float(re.sub(r"[^\d.\-]","",str(v)))
 except (TypeError,ValueError):return 0
fmt=lambda x:x.strftime("%d/%m/%y")
response=api("POST","/SearchApi/Search",json={"ActiveQuickSearch":False,"ActiveMichraz":False,
"VaadaDate":{"from":fmt(since),"to":fmt(now)}})
allrows=response if isinstance(response,list) else response.get("results") or response.get("Results") or response.get("data") or []
if not isinstance(allrows,list):raise ValueError("Unexpected search schema")
recent=sorted([(date(t.get("VaadaDate")) or date(t.get("PirsumDate")),t) for t in allrows
 if isinstance(t,dict) and (date(t.get("VaadaDate")) or date(t.get("PirsumDate"))) and
 (date(t.get("VaadaDate")) or date(t.get("PirsumDate")))>=since],key=lambda x:x[0],reverse=True)
print("SEARCH_TOTAL",len(allrows),"IN_90_DAYS",len(recent),flush=True)
if len(recent)>400:raise RuntimeError("Over RMI_MAX_DETAILS=400; can't certify complete coverage")
unique=[];ids=set();duplicate_count=0
for date_,row in recent:
 mid=row.get("MichrazID")
 if mid is None:raise RuntimeError("Recent record without tender ID")
 if mid in ids:duplicate_count+=1;continue
 ids.add(mid);unique.append((date_,row))
sett=api("GET","/YeshuvimApi/Get")
if not isinstance(sett,list):raise RuntimeError("Invalid settlement map")
cities={str(int(x["mtysvSemelYishuv"])):x["mtysvShemYishuv"] for x in sett
 if isinstance(x,dict) and x.get("mtysvSemelYishuv") is not None and x.get("mtysvShemYishuv")}
if len(cities)<1400:raise RuntimeError("Incomplete settlement map")
out=[];failures=[];no_tik=[];status=Counter();tenders_with_winners=0
for i,(committee,summary) in enumerate(unique,1):
 mid=summary["MichrazID"];status[str(summary.get("StatusMichraz"))]+=1
 try:
  d=api("GET","/MichrazDetailsApi/Get",params={"michrazID":mid})
  if not isinstance(d,dict) or str(d.get("MichrazID"))!=str(mid):
   raise ValueError("Unexpected detail ID/schema")
  plots=d.get("Tik")
  if not isinstance(plots,list):raise ValueError("Missing or non-list Tik")
  before=len(out)
  for index,p in enumerate(plots):
   if not isinstance(p,dict):continue
   winner=str(p.get("ShemZoche") or "").strip()
   if len(winner)<2 or re.search(r"^אין |לא בטווח|לא תקינ|זכה במתחם אחר|בוטל|לא הוגשו|ללא זוכה",winner):continue
   bid=amount(p.get("SchumZchiya"));dev=amount(p.get("HotzaotPituach"))
   units=d.get("YechidotDiur") or 0
   if not (bid+dev or units):continue
   code=str(d.get("KodYeshuv") or summary.get("KodYeshuv") or "")
   out.append({"committee_date":committee.isoformat(),"tender_id":str(mid),
    "tender_name":d.get("MichrazName") or summary.get("MichrazName"),"city":code,
    "city_name":cities.get(code,""),"complex":p.get("MitchamName") or "",
    "winner":winner,"price":bid,"development_costs":dev,"total_cost":bid+dev,"units":units,
    "json_path":f"/Tik[{index}]"})
  if len(out)>before:tenders_with_winners+=1
 except Exception as e:
  failures.append({"id":str(mid),"error":str(e)[:200]})
  print("DETAIL_FAILURE",mid,str(e)[:80],flush=True)
 time.sleep(.6)
 if i%25==0 or i==len(unique):
  print("PROGRESS",i,len(unique),"WINNER_ROWS",len(out),"FAILURES",len(failures),flush=True)
p=Path("rmi_full_live");p.mkdir(exist_ok=True)
keys=["committee_date","tender_id","tender_name","city","city_name","complex",
"winner","price","development_costs","total_cost","units","json_path"]
with (p/"winners_90d.csv").open("w",encoding="utf-8-sig",newline="") as f:
 w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(out)
metrics={"collected_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
 "since":since.isoformat(),"to":now.isoformat(),"search_total":len(allrows),
 "recent_records":len(recent),"unique_recent_tenders":len(unique),
 "duplicate_tender_ids":duplicate_count,"details_ok":len(unique)-len(failures),
 "detail_failures":failures,"winner_rows":len(out),
 "tenders_with_winners":tenders_with_winners,"missing_city_names":sum(not x["city_name"] for x in out),
 "settlement_codes":len(cities),"status_counts":status,
 "complete":not failures and len(unique)<=400}
(p/"metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding="utf-8")
print("FINAL_METRICS",json.dumps({k:v for k,v in metrics.items() if k!="detail_failures"},ensure_ascii=False),flush=True)
if failures:raise SystemExit(1)
