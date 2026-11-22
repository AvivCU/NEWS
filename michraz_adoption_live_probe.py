"""Research only: verify current RMI public API and official public CSV download route.
No /api/ calls on data.gov.il; no authentication; read-only public source checks.
"""
import json,urllib.request,urllib.error,urllib.parse
from pathlib import Path
from datetime import datetime,timezone
DATA={
 "beer_sheva_csv_one":"https://data.gov.il/dataset/tender-br7/resource/6a281768-6327-420b-a1c5-fb84af1fa8ae/download/datafile.csv",
 "beer_sheva_csv_two":"https://data.gov.il/dataset/tender-br7/resource/6a281768-6327-420b-a1c5-fb84af1fa8ae/download/tender-br7.csv",
 "beer_sheva_resource_ui":"https://data.gov.il/he/datasets/beer-sheva/tender-br7/0e41e810-b738-4219-a2c0-f0e13a3feeb7",
}
res={"checked_utc":datetime.now(timezone.utc).isoformat(),"checks":{}}
for name,url in DATA.items():
 info={"url":url}
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Rosario public-source integrity audit 1.0","Accept":"text/csv,application/octet-stream,text/html,*/*"})
  with urllib.request.urlopen(req,timeout=20) as r:
   body=r.read(1500000)
   info.update(status=r.status,content_type=r.headers.get("content-type"),size_read=len(body),final_url=r.geturl(),
              sample=body[:180].decode("utf-8","replace"))
 except Exception as e:info["error"]=str(e)[:160]
 res["checks"][name]=info
 print("PROBE",name,json.dumps(info,ensure_ascii=False)[:700],flush=True)
url="https://apps.land.gov.il/MichrazimSite/api/YeshuvimApi/Get"
try:
 req=urllib.request.Request(url,headers={"User-Agent":"Rosario public-source integrity audit 1.0","Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=25) as r:
  raw=r.read(800000);info={"http":r.status,"size_read":len(raw)}
 val=json.loads(raw)
 if isinstance(val,list):
  info["records"]=len(val);info["keys"]=list(val[0])[:20] if val and isinstance(val[0],dict) else []
 elif isinstance(val,dict):
  info["keys"]=list(val)[:25]
  info["records"]=len(val)
 else:info["shape"]=type(val).__name__
 res["checks"]["rmi_yeshuvim_current"]=info
 print("PROBE rmi_yeshuvim_current",json.dumps(info,ensure_ascii=False),flush=True)
except Exception as e:
 res["checks"]["rmi_yeshuvim_current"]={"error":str(e)[:200]}
 print("PROBE rmi_yeshuvim_current ERROR",str(e)[:200],flush=True)
Path("michraz_adoption_live_report.json").write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding="utf-8")
