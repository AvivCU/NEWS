"""Full, read-only audit of public government datasets. Aggregates only; no company watchlists.
Run on GitHub Actions. Output: full_dataset_report.json / .md, not raw data.
"""
import collections
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DATASETS={
 "procurement_exemptions":{
  "id":"65c8fced-c50c-400e-94fb-ef1a208c43e5",
  "fields":["_id","תאריך פרסום","תאריך עדכון","שם ספק","מספר חפ ספק","היקף כספי","מטבע","מהות החלטה","סוג הליך","שם הליך","מספר פרסום"]},
 "procurement_tenders":{
  "id":"7038b3e6-a74d-442e-b16b-466c8196124a",
  "fields":["_id","תאריך פרסום","תאריך עדכון","שם ספק זוכה","מספר חפ ספק","סטטוס","שם הליך","מספר פרסום"]},
 "emission_permits":{
  "id":"c84b4fa4-9102-4fb8-93ff-c21ecd37566f",
  "fields":["_id","GovXMainTitle","SvivaDate","EnvCurrentStagePermits","EnvSector","EnvSettlement","Title","PermitNumber"]},
 "environmental_factories":{
  "id":"7ad8ddc7-87f4-45f9-84e4-d7f972662153",
  "fields":["_id","MisparTaagidShutfutMenifa","ShemTaagidShutfut","ShnatDivuach","MisparAtarSvivati","AnafAtarSvivati","ShemAtarSvivatiMenifa","TaarichDivuahBefoal"]},
 "environmental_multiyear":{
  "id":"87c88ab8-3076-4422-a8fb-27bc57ce4b76",
  "fields":["_id","MisparTaagidShutfutMenifa","ShemTaagidShutfut","ShnatDivuach","MisparAtarSvivati","MezahemBeplita","KamutPlita","TaarichDivuahBefoal"]},
}
BASE="https://data.gov.il/api/3/action/datastore_search"
PAGE_SIZE=10000
def fetch(resource_id,fields,offset,limit=PAGE_SIZE):
 query=urlencode({"resource_id":resource_id,"limit":limit,"offset":offset,"fields":",".join(fields)})
 request=Request(BASE+"?"+query,headers={"Accept":"application/json","User-Agent":"Rosario-full-public-source-audit/1.0"})
 for attempt in range(5):
  try:
   with urlopen(request,timeout=35) as response:
    payload=json.load(response)
   if not payload.get("success") or not isinstance(payload.get("result",{}).get("records"),list):
    raise ValueError("CKAN returned unsuccessful response")
   return payload["result"]
  except (HTTPError,URLError,TimeoutError,OSError,ValueError) as e:
   if attempt==4: raise
   time.sleep(min(35, (2 ** attempt) * 3))
def year_of(value):
 if value is None:return None
 s=str(value)
 m=re.search(r"(?<!\d)(20\d\d|19\d\d)(?!\d)",s)
 if not m:return None
 y=int(m.group(1))
 return str(y) if 1990<=y<=2030 else None
def name_id(row,key):
 if key=="procurement_exemptions":return row.get("שם ספק"),row.get("מספר חפ ספק")
 if key=="procurement_tenders":return row.get("שם ספק זוכה"),row.get("מספר חפ ספק")
 if key=="emission_permits":return row.get("GovXMainTitle"),None
 return row.get("ShemTaagidShutfut"),row.get("MisparTaagidShutfutMenifa")
def nonempty(x):
 return x is not None and str(x).strip() not in ("","(חסר)","nan","None")
def analyze(key,spec):
 years=collections.Counter()
 names=set(); ids=set(); pairs=set(); sites=set()
 records=0; named=0; with_id=0; with_sum=0; sum_in_ils=0.0
 recent_examples=[]; latest_date=""; last_offset=0; err=None; total=None
 max_year=None; max_year_examples=[]
 while True:
  try:
   page=fetch(spec["id"],spec["fields"],last_offset)
  except Exception as e:
   err=type(e).__name__+": "+str(e)[:200]
   break
  rows=page["records"]; total=page.get("total",total)
  if not rows:break
  for r in rows:
   records+=1
   name,hp=name_id(r,key)
   if nonempty(name):
    named+=1; names.add(str(name).strip())
   if nonempty(hp):
    with_id+=1;ids.add(str(hp).strip())
   if nonempty(name) and nonempty(hp):
    pairs.add((str(hp).strip(),str(name).strip()))
   if key=="procurement_exemptions":
    y=year_of(r.get("תאריך פרסום"))
    amount=r.get("היקף כספי")
    if nonempty(amount):
     with_sum+=1
     if str(r.get("מטבע","")).strip() in ("₪","ILS","שקל","שח","ש״ח","ש\"ח"):
      try:sum_in_ils+=float(str(amount).replace(",",""))
      except ValueError:pass
   elif key=="procurement_tenders":y=year_of(r.get("תאריך פרסום"))
   elif key=="emission_permits":y=year_of(r.get("SvivaDate"))
   else:
    y=year_of(r.get("ShnatDivuach"))
    if nonempty(r.get("MisparAtarSvivati")):sites.add(str(r["MisparAtarSvivati"]))
   if y:
    years[y]+=1
    if max_year is None or y>max_year:
     max_year=y;max_year_examples=[]
    if y==max_year and len(max_year_examples)<8 and nonempty(name):
     item={"name":str(name)[:120],"year":y}
     if nonempty(hp):item["company_id"]=str(hp)[:20]
     if key=="procurement_exemptions":
      item["subject"]=str(r.get("שם הליך") or "")[:150]
      item["amount"]=str(r.get("היקף כספי") or "")[:40]
      item["publication"]=str(r.get("תאריך פרסום") or "")[:30]
     if key=="procurement_tenders":item["subject"]=str(r.get("שם הליך") or "")[:150]
     if key=="emission_permits":
      item["permit_stage"]=str(r.get("EnvCurrentStagePermits") or "")[:80]
      item["document"]=str(r.get("Title") or "")[:100]
     max_year_examples.append(item)
  last_offset+=len(rows)
  if last_offset%20000< PAGE_SIZE or (total and last_offset>=total):
   print(f"{key}: {last_offset}/{total}",flush=True)
  if total is not None and last_offset>=int(total):break
  if len(rows)<PAGE_SIZE:break
  time.sleep(1.4)
 return {
  "resource_id":spec["id"],"reported_total":total,"rows_scanned":records,
  "complete":err is None and (total is None or records>=total),"error":err,
  "with_company_name_rows":named,"unique_company_names":len(names),
  "with_company_id_rows":with_id,"unique_company_ids":len(ids),
  "unique_company_id_name_pairs":len(pairs),"unique_sites":len(sites) if sites else None,
  "rows_with_amount":with_sum if key=="procurement_exemptions" else None,
  "years":dict(sorted(years.items())), "latest_year":max_year,
  "latest_year_examples":max_year_examples,
 }
def main():
 results={"generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
 "scope":"full public datasets; excludes private watchlist; NOT proof of private ownership or >NIS 100m revenue",
 "datasets":{}}
 for key,spec in DATASETS.items():
  print("START",key,flush=True)
  results["datasets"][key]=analyze(key,spec)
  x=results["datasets"][key]
  print(f'DONE {key} scanned={x["rows_scanned"]} complete={x["complete"]} latest_year={x["latest_year"]} company_ids={x["unique_company_ids"]}',flush=True)
  Path("full_dataset_report.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
 lines=["# Rosario — full official dataset scan", "", "Generated UTC: "+results["generated_utc"], "", "No private CRM/watchlist data were uploaded. No automatic new leads or revenue claims.", ""]
 for key,x in results["datasets"].items():
  lines += [f"## {key}", f'- Complete: {x["complete"]} (scanned {x["rows_scanned"]} / declared {x["reported_total"]})',
   f'- Identified company names (unique): {x["unique_company_names"]}; IDs (unique): {x["unique_company_ids"]}',
   f'- Latest data year: {x["latest_year"]}', f'- Years: {json.dumps(x["years"],ensure_ascii=False)}', ""]
  if x["error"]:lines.append("- Error: "+x["error"])
 Path("full_dataset_report.md").write_text("\n".join(lines),encoding="utf-8")
 if any(not x["complete"] for x in results["datasets"].values()):sys.exit(1)
if __name__=="__main__":main()
