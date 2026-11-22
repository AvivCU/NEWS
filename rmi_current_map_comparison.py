"""Compare public live RMI settlement codes against pinned open-source mapping."""
import json, urllib.request
from pathlib import Path
from datetime import datetime,timezone
upstream=json.loads(Path("michraz/src/michraz/sources/data/rmi_settlements.json").read_text("utf8"))
url="https://apps.land.gov.il/MichrazimSite/api/YeshuvimApi/Get"
req=urllib.request.Request(url,headers={"User-Agent":"Rosario Public Official Source Validation","Accept":"application/json"})
with urllib.request.urlopen(req,timeout=40) as r:
 raw=r.read(5000000)
 print("LIVE_STATUS",r.status,"BYTES",len(raw),flush=True)
rows=json.loads(raw)
assert isinstance(rows,list)
print("LIVE_ROWS",len(rows))
sample=rows[0]
print("LABEL_KEYS",[x for x in sample if "shem" in x.lower() or "semel" in x.lower()])
for row in rows[:2]:print("LABEL_SAMPLES",{k:v for k,v in row.items() if "shem" in k.lower() or "semel" in k.lower()})
label_key=next((k for k in sample if "shem" in k.lower() and "yishuv" in k.lower()),None)
code_key="mtysvSemelYishuv"
print("NAME_KEY",label_key)
assert label_key and code_key in sample
mapping={}
duplicates=[]
for r in rows:
 code=r.get(code_key);name=r.get(label_key)
 if code is None or not isinstance(name,str) or not name.strip():continue
 try: key=str(int(code))
 except (TypeError,ValueError):continue
 if key in mapping and mapping[key]!=name.strip():
  duplicates.append({"key":key,"before":mapping[key],"after":name.strip()})
 mapping[key]=name.strip()
prior=upstream["settlements"]
added={k:v for k,v in mapping.items() if k not in prior}
removed={k:v for k,v in prior.items() if k not in mapping}
renamed={k:[prior[k],v] for k,v in mapping.items() if k in prior and prior[k]!=v}
print("DISTINCT_CODES",len(mapping),"UPSTREAM_CODES",len(prior),"ADDED",added,"REMOVED",removed,"RENAMED_SAMPLE",dict(list(renamed.items())[:12]),"RENAMED_COUNT",len(renamed),"DUPLICATES",duplicates[:5],flush=True)
report={"checked_utc":datetime.now(timezone.utc).isoformat(),"api":url,"record_count":len(rows),"distinct_codes":len(mapping),"upstream_count":len(prior),"added":added,"removed":removed,"changed":renamed,"duplicates":duplicates}
Path("rmi_current_vs_upstream.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
if len(mapping)<1400 or len(duplicates)>0:raise RuntimeError("Source lookup integrity check failed")
new={"version":1,"source":url,"fetched":datetime.now(timezone.utc).date().isoformat(),"settlements":mapping}
Path("rmi_settlements_current.json").write_text(json.dumps(new,ensure_ascii=False,separators=(",",":")),encoding="utf8")
