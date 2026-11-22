"""Verify 2026 primary-source PDF documents from blocked government pages."""
import json,urllib.request,datetime
from pathlib import Path
PDFS={
"gov_2026_air_permit":"https://www.gov.il/BlobFolder/dynamiccollectorresultitem/aot_bgc_2025/he/air_emission_permits_2026_permitchange_aot_2025.pdf",
"nta_2026_single_supplier":"https://www.nta.co.il/media/3zed4jg3/7126-%D7%94%D7%95%D7%93%D7%A2%D7%94-%D7%A2%D7%9C-%D7%9B%D7%95%D7%95%D7%A0%D7%94-%D7%9C%D7%94%D7%AA%D7%A7%D7%A9%D7%A8-%D7%A2%D7%9D-%D7%A1%D7%A4%D7%A7-%D7%99%D7%97%D7%99%D7%93.pdf"
}
results={"time":datetime.datetime.now(datetime.timezone.utc).isoformat(),"documents":{}}
for key,url in PDFS.items():
 row={"url":url}
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Rosario public document verification","Accept":"application/pdf"})
  with urllib.request.urlopen(req,timeout=30) as res:
   b=res.read(1000000)
   row.update({"status":res.status,"type":res.headers.get("Content-Type"),"pdf_magic":b.startswith(b"%PDF"),"bytes_read":len(b)})
 except Exception as e:row["error"]=repr(e)[:250]
 results["documents"][key]=row
 print(key,json.dumps(row,ensure_ascii=False),flush=True)
Path("official_2026_pdf_access.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf8")
