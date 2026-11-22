"""Test publicly advertised GET endpoints used by the official Rail tenders web app."""
import json, urllib.request, urllib.parse, urllib.robotparser,datetime
from pathlib import Path
BASE="https://rail-api.rail.co.il/common/api/v1/Tenders/"
def request(path):
 url=BASE+path
 req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"Rosario-Feeds public-readonly tender source verification"})
 with urllib.request.urlopen(req,timeout=28) as r:
  raw=r.read(3000000)
  info={"status":r.status,"content_type":r.headers.get("Content-Type"),"size":len(raw),"url":url}
  try:obj=json.loads(raw)
  except Exception as e:info["error"]="JSON decode: "+str(e);return info,None
  info["container_type"]=type(obj).__name__
  if isinstance(obj,dict):info["keys"]=list(obj)[:25]
  else:info["items"]=len(obj)
  return info,obj
def value(obj):
 if isinstance(obj,list):return obj
 if isinstance(obj,dict):
  for key in ["data","Data","result","Result","items","Items","content","Content","tenderTypes","TenderTypes"]:
   v=obj.get(key)
   if isinstance(v,list):return v
   if isinstance(v,dict):
    x=value(v)
    if x:return x
 return []
def main():
 result={"checked_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"requests":[]}
 # The API host is public; respect its published robots instructions, when present.
 rp=urllib.robotparser.RobotFileParser()
 rp.set_url("https://rail-api.rail.co.il/robots.txt")
 try:rp.read()
 except Exception as e:print("ROBOTS_FETCH_ERROR",str(e)[:120],flush=True)
 if not rp.can_fetch("Rosario-Feeds",BASE+"GetTenderTypes"):
  result["blocked_by_robots"]=True
  Path("rail_api_live_report.json").write_text(json.dumps(result,indent=2))
  print("ROBOTS_DISALLOW",flush=True)
  return
 try:
  info,obj=request("GetTenderTypes")
  types=value(obj)
  info["samples"]=types[:12]
  result["requests"].append(info)
  print("TENDER_TYPES",json.dumps(info,ensure_ascii=False)[:4500],flush=True)
  valid=[]
  for t in types:
   if isinstance(t,(int,str)):v=t
   elif isinstance(t,dict):v=next((t[k] for k in ["id","Id","type","Type","value","Value","typeId","TypeId","code","Code"] if k in t),None)
   else:v=None
   if v is not None and str(v).strip():valid.append(str(v))
  for v in valid[:3]:
   path="GetTendersByType?type="+urllib.parse.quote(v)
   if not rp.can_fetch("Rosario-Feeds",BASE+path):continue
   info,listing=request(path)
   rows=value(listing)
   info["type"]=v
   info["record_count_in_response"]=len(rows)
   info["samples"]=rows[:2]
   result["requests"].append(info)
   print("TENDER_LIST",json.dumps(info,ensure_ascii=False)[:5000],flush=True)
 except Exception as e:
  result["error"]=type(e).__name__+": "+str(e)[:350]
  print("ERROR",result["error"],flush=True)
 Path("rail_api_live_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":main()
