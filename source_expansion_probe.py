"""Read-only connectivity probe of newly identified official public sources (no private data).
Only GETs public pages/APIs; no bypass, credentials, or writes to upstream sites.
"""
import json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

SOURCES={
 "iaa_active":"https://www.iaa.gov.il/tenders-and-contracts/active-tenders/",
 "iaa_awards":"https://www.iaa.gov.il/tenders-and-contracts/results-of-tenders/",
 "nta_single_supplier":"https://www.nta.co.il/tenders3/",
 "nta_tenders":"https://www.nta.co.il/tenders?p=1",
 "ayalon_exemptions":"https://www.ayalonhw.co.il/tenders/communications/",
 "rail_tenders":"https://www.rail.co.il/tenders/pages/open.aspx",
 "innovation_awards_2026":"https://innovationisrael.org.il/invested-companies-2026/",
 "innovation_exemptions":"https://innovationisrael.org.il/tender-engagments-exempt/",
 "xplan_services":"https://ags.iplan.gov.il/services/?f=PlanningPublic",
 "xplan_map_json":"https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer?f=pjson",
 "xplan_count":"https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer/1/query?where=1%3D1&returnCountOnly=true&f=json",
 "gov_foi_reports":"https://www.gov.il/he/departments/units/freedom_of__information_law",
 "env_permits_listing":"https://www.gov.il/he/departments/dynamiccollectors/permit_emission",
}
BLOCK=("access denied","just a moment","attention required","captcha","request rejected","please enable javascript","רק רגע")
MARKERS=["שם ספק/לקוח","שם ספק","זוכה","תאריך החלטה","2026","MapServer","features","count","התקשרויות","מכרז"]
def run():
 out={"checked_utc":datetime.now(timezone.utc).isoformat(),"results":{}}
 for name,url in SOURCES.items():
  row={"url":url}
  try:
   req=Request(url,headers={"Accept":"text/html,application/json,*/*","User-Agent":"Rosario-Feeds-public-source-audit/1.0"})
   with urlopen(req,timeout=30) as r:
    raw=r.read(1400000)
    row.update({"http":r.status,"bytes_read":len(raw),"content_type":r.headers.get("Content-Type"),"final_url":r.geturl()})
   text=raw.decode("utf-8","replace")
   low=text.lower()
   row["block_marker"]=next((m for m in BLOCK if m in low[:12000]),None)
   m=re.search(r"<title[^>]*>(.*?)</title",text,re.I|re.S)
   row["title"]=re.sub(r"\s+"," ",m.group(1)).strip()[:100] if m else ""
   row["markers"]={m:text.count(m) for m in MARKERS if m in text}
   row["sample_dates_2026"]=list(dict.fromkeys(re.findall(r"(?:[0-3]?\d[/\.][01]?\d[/\.]2026|2026-[01]\d-[0-3]\d)",text)))[:6]
   if "json" in (row["content_type"] or "").lower() or name.endswith("_json") or name.endswith("_count"):
    try:
     obj=json.loads(text);row["json_keys"]=list(obj)[:15] if isinstance(obj,dict) else []
     if isinstance(obj,dict):
      row["json_count"]=obj.get("count")
      row["json_error"]=obj.get("error")
      row["layers"]= [{"id":v.get("id"),"name":v.get("name")} for v in obj.get("layers",[])[:7]]
    except Exception as e:row["json_parse_error"]=str(e)[:100]
   row["verdict"]="blocked" if row["http"]!=200 or row["block_marker"] else "content" if len(raw)>1000 else "empty"
  except (HTTPError,URLError,TimeoutError,ValueError,OSError) as e:
   row.update({"verdict":"failed","error":str(e)[:200]})
  out["results"][name]=row
  print(name,json.dumps(row,ensure_ascii=False)[:1800],flush=True)
 Path("source_expansion_probe.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":run()
