"""Discover official CKAN datasets and probe *resource* availability on Github Actions.
Public metadata only. Does not fetch entire files or modify external resources.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE="https://data.gov.il/api/3/action/"
QUERIES={
 "procurement_exemptions":["דוח התקשרויות בפטור","exemptions"],
 "procurement_tenders":["דוח מכרזים","tenders"],
 "emission_permits":["מאגר היתרי פליטה לאוויר","permitemissionforzovar"],
 "environmental_registry":["מפלס מפעלים","maflasmultiannualforzover"],
}
def get(url, cap=450000, timeout=18):
 req=Request(url,headers={"User-Agent":"Rosario-source-audit/1.0 (metadata and small samples)","Accept":"application/json,*/*"})
 try:
  with urlopen(req,timeout=timeout) as r:
   body=r.read(cap)
   return {"http":r.status,"body":body,"content_type":r.headers.get("Content-Type",""),"final_url":r.geturl()}
 except HTTPError as e:
  return {"http":e.code,"error":str(e)}
 except (URLError,TimeoutError,OSError) as e:
  return {"http":None,"error":str(e)[:160]}
def ck(url):
 raw=get(url)
 out={"http":raw["http"]}
 if "error" in raw:
  out["error"]=raw["error"]
 if raw["http"]==200:
  try:
   j=json.loads(raw["body"])
   out["success"]=j.get("success")
   out["result"]=j.get("result",{})
  except (ValueError,UnicodeError) as e:
   out["error"]="invalid JSON: "+str(e)
 return out

def run():
 result={"utc":datetime.now(timezone.utc).isoformat(),"method":"CKAN public API, HEAD-like capped GET on 1-2 resources; no private data","datasets":{}}
 for group,queries in QUERIES.items():
  found={}
  statuses=[]
  for q in queries:
   uri=BASE+"package_search?"+urlencode({"q":q,"rows":15})
   data=ck(uri)
   statuses.append({"query":q,"http":data["http"],"success":data.get("success"),"count":data.get("result",{}).get("count")})
   if data.get("success"):
    for p in data.get("result",{}).get("results",[]):
     if p.get("id"): found[p["id"]]=p
   time.sleep(.2)
  candidates=[]
  for p in list(found.values())[:30]:
   resources=[]
   for r in p.get("resources",[])[:12]:
    resources.append({"id":r.get("id"),"name":r.get("name"),"format":r.get("format"),"url":r.get("url"),"last_modified":r.get("last_modified"),"created":r.get("created"),"datastore_active":r.get("datastore_active")})
   candidates.append({"id":p.get("id"),"name":p.get("name"),"title":p.get("title"),"metadata_modified":p.get("metadata_modified"),"resources":resources})
  result["datasets"][group]={"searches":statuses,"candidates":candidates}
  print(f'{group}: search={[(x["http"],x["count"]) for x in statuses]} packages={len(candidates)}',flush=True)
  # Only direct sample for the first two resources from best possible candidates.
  if candidates:
   for c in candidates[:2]:
    probes=[]
    for r in c["resources"][:2]:
     if not r.get("url"): continue
     u=r["url"]
     if not u.startswith(("https://data.gov.il/","https://www.data.gov.il/","https://storage.googleapis.com/")):
      probes.append({"id":r.get("id"),"state":"external_url_not_tested","host_url":u[:250]});continue
     v=get(u,cap=4096,timeout=12)
     probes.append({"id":r.get("id"),"http":v["http"],"content_type":v.get("content_type"),"read_bytes":len(v.get("body",b"")),"error":v.get("error")})
     if r.get("id"):
      q=ck(BASE+"datastore_search?"+urlencode({"resource_id":r["id"],"limit":1}))
      probes[-1]["datastore"]={"http":q["http"],"success":q.get("success"),"total":q.get("result",{}).get("total"),"fields":[x.get("id") for x in q.get("result",{}).get("fields",[])][:30]}
     time.sleep(.2)
    c["probes"]=probes
 Path("ckan_discovery.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":
 run()
