"""Read-only audit of public official sources from GitHub Actions.
Does not access any private Rosario company records.
"""
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SOURCES = {
  "innovation_authority": "https://innovationisrael.org.il/invested-companies-2026/",
  "procurement_exemptions": "https://data.gov.il/he/datasets/governmentprocurementadministration/exemptions/65c8fced-c50c-400e-94fb-ef1a208c43e5",
  "procurement_tenders": "https://data.gov.il/he/datasets/governmentprocurementadministration/tenders",
  "emission_permits": "https://data.gov.il/he/datasets/ministry_of_the_environment/permitemissionforzovar",
  "environmental_registry": "https://data.gov.il/he/datasets/ministry_of_the_environment/maflasmultiannualforzover",
  "data_gov_ckan_api": "https://data.gov.il/api/3/action/package_search?rows=1",
  "data_gov_renewal_api": "https://data.gov.il/api/3/action/datastore_search?resource_id=f65a0daf-f737-49c5-9424-d378d52104f5&limit=1",
  "ourmoney_docs": "https://ourmoneyil.com/api/",
  "iaa_active_tenders": "https://www.iaa.gov.il/tenders-and-contracts/active-tenders/",
  "iaa_archive": "https://www.iaa.gov.il/tenders-and-contracts/tenders-archive/",
}
CUES = {
 "innovation_authority": ("חברות", "השקעה", "innovation"),
 "procurement_exemptions": ("התקשרות", "פטור"),
 "procurement_tenders": ("מכרז", "רכש"),
 "emission_permits": ("פליטה", "היתר"),
 "environmental_registry": ("מפל", "מפעל"),
 "data_gov_ckan_api": ('"success":true', '"result"'),
 "data_gov_renewal_api": ('"records"', '"result"'),
 "ourmoney_docs": ("api", "supplier"),
 "iaa_active_tenders": ("ספק", "פטור", "מכרז"),
 "iaa_archive": ("מכרז", "ארכיון"),
}
def classify(status, body, cues):
 text = body[:500000].decode("utf-8", "replace").lower()
 first = text[:6000]
 if status in (401, 403, 429, 503):
  return "blocked"
 if status >= 400:
  return "http_error"
 if not text.strip():
  return "empty"
 # Only clear signs of a *current* challenge page, not arbitrary words in a full site.
 title = re.search(r"<title[^>]*>(.*?)</title>", first, re.I | re.S)
 title_text = html.unescape(re.sub(r"<[^>]+>", "", title.group(1))).lower().strip() if title else ""
 if any(x in title_text for x in ("just a moment", "access denied", "attention required", "captcha", "checking your browser")):
  return "blocked"
 if "cf-chl-widget" in first or "cf_chl_opt" in first:
  return "blocked"
 return "content_visible" if any(x.lower() in text for x in cues) else "reachable_unverified"

def run():
 results=[]
 for key, url in SOURCES.items():
  row={"source":key,"url":url}
  try:
   request=Request(url,headers={"User-Agent":"Rosario-Feeds-audit/1.0 (+public read-only source test)","Accept":"text/html,application/json,*/*"})
   with urlopen(request,timeout=20) as res:
    body=res.read(500000)
    row.update(http=res.status,bytes=len(body),content_type=res.headers.get("Content-Type",""),final_url=res.geturl())
    row["state"]=classify(res.status,body,CUES[key])
    snippet=body[:15000].decode("utf-8","replace")
    title=re.search(r"<title[^>]*>(.*?)</title>",snippet,re.I|re.S)
    row["page_title"]=html.unescape(re.sub(r"<[^>]+>","",title.group(1))).strip()[:160] if title else None
    if "json" in row["content_type"].lower():
     try:
      data=json.loads(body)
      row["json_success"]=data.get("success") if isinstance(data,dict) else None
      row["json_result_keys"]=list(data.get("result",{}))[:10] if isinstance(data,dict) and isinstance(data.get("result"),dict) else []
     except (ValueError,TypeError):
      row["json_parse_error"]=True
  except HTTPError as e:
   row.update(http=e.code,state="blocked" if e.code in (401,403,429,503) else "http_error")
  except (URLError,TimeoutError,OSError) as e:
   row.update(state="network_error",error=f"{type(e).__name__}: {str(e)[:140]}")
  results.append(row)
  print(f'{key}: {row["state"]} HTTP={row.get("http","-")} bytes={row.get("bytes",0)} title={row.get("page_title","")}',flush=True)
  time.sleep(.3)
 Path("audit.json").write_text(json.dumps({"utc":datetime.now(timezone.utc).isoformat(),"scope":"read-only HTTP; not proof of data completeness","results":results},ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":
 run()
