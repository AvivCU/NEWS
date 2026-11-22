"""Read real records from four official data.gov.il datasets using the public CKAN API.

No private/company-watchlist inputs. Limit one page per resource (default 3, maximum 20).
Works when the data.gov.il webpage and direct CSV return HTTP 403.
"""
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
DATASETS={
 "procurement_exemptions":"65c8fced-c50c-400e-94fb-ef1a208c43e5",
 "procurement_tenders":"7038b3e6-a74d-442e-b16b-466c8196124a",
 "emission_permits":"c84b4fa4-9102-4fb8-93ff-c21ecd37566f",
 "environmental_factories":"7ad8ddc7-87f4-45f9-84e4-d7f972662153",
 "environmental_multiyear":"87c88ab8-3076-4422-a8fb-27bc57ce4b76",
}
API="https://data.gov.il/api/3/action/datastore_search"
def fetch(resource_id,limit=3,offset=0):
 if not 1<=limit<=20: raise ValueError("limit must be within 1..20")
 if offset<0: raise ValueError("offset must be nonnegative")
 url=API+"?"+urlencode({"resource_id":resource_id,"limit":limit,"offset":offset})
 request=Request(url,headers={"User-Agent":"Rosario official datasets read-only audit","Accept":"application/json"})
 with urlopen(request,timeout=25) as response:
  obj=json.load(response)
 if not obj.get("success") or not isinstance(obj.get("result",{}).get("records"),list):
  raise ValueError("Datastore returned invalid data")
 result=obj["result"]
 return {"resource_id":resource_id,"total":result.get("total"),"fields":[f.get("id") for f in result.get("fields",[])],"records":result["records"]}
def main():
 out={"checked_at_utc":datetime.now(timezone.utc).isoformat(),"datasets":{}}
 for key,rid in DATASETS.items():
  try:
   result=fetch(rid)
   out["datasets"][key]=result
   print(f'{key}: OK total={result["total"]}, sample={len(result["records"])}, fields={len(result["fields"])}',flush=True)
  except Exception as exc:
   out["datasets"][key]={"error":type(exc).__name__+": "+str(exc)[:180]}
   print(f'{key}: FAILED {exc}',flush=True)
 Path("dataset_samples.json").write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
 if any("error" in v for v in out["datasets"].values()): sys.exit(1)
if __name__=="__main__":
 main()
