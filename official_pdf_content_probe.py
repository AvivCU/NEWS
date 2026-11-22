"""Read-only validation of three 2026 official PDF documents, not a monitoring feed."""
from pathlib import Path
import hashlib,json,re,urllib.request
import fitz
URLS={
"nta_supplier_intent":"https://www.nta.co.il/media/3zed4jg3/7126-%D7%94%D7%95%D7%93%D7%A2%D7%94-%D7%A2%D7%9C-%D7%9B%D7%95%D7%95%D7%A0%D7%94-%D7%9C%D7%94%D7%AA%D7%A7%D7%A9%D7%A8-%D7%A2%D7%9D-%D7%A1%D7%A4%D7%A7-%D7%99%D7%97%D7%99%D7%93.pdf",
"rail_public_tender":"https://tender.rail.co.il/tmedia/AllTenders/b25ba039-1592-43ec-0b96-08decb72c0f0/%D7%9E%D7%95%D7%93%D7%A2%D7%94%20%D7%9C%D7%A2%D7%99%D7%AA%D7%95%D7%9F.pdf",
"gov_environmental_permit":"https://www.gov.il/BlobFolder/dynamiccollectorresultitem/aot_bgc_2025/he/air_emission_permits_2026_permitchange_aot_2025.pdf",
}
def run():
 out={}
 for name,url in URLS.items():
  row={"source_url":url}
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Rosario public source PDF audit","Accept":"application/pdf"})
   with urllib.request.urlopen(req,timeout=30) as r:
    raw=r.read(10000000)
    row["status"]=r.status
   if not raw.startswith(b"%PDF"):raise ValueError("not PDF")
   row["size"]=len(raw);row["sha256"]=hashlib.sha256(raw).hexdigest()
   with fitz.open(stream=raw,filetype="pdf") as pdf:
    row["pages"]=len(pdf)
    txt=" ".join(p.get_text() for p in list(pdf)[:min(len(pdf),8)])
   row["text_chars"]=len(txt)
   row["sample"]=re.sub(r"\s+"," ",txt)[:300]
   row["classification"]=("single_supplier_intent" if re.search("כוונה להתקשר|ספק יחיד|כוונה להתקשרות",txt) else
      "environmental_permit" if "היתר פליטה" in txt else
      "tender" if re.search("מכרז|tender",txt,re.I) else "unclassified")
  except Exception as e:row["error"]=repr(e)[:150]
  out[name]=row
  print(name,json.dumps(row,ensure_ascii=False)[:1100],flush=True)
 Path("official_pdf_content_probe.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf8")
if __name__=="__main__":run()
