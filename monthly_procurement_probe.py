"""Check the live, monthly government procurement ZIP exports; public information only."""
import io, json, re, zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

FILES={
 "tenders":"https://mr.gov.il/ilgstorefront/medias/Tenders-01112026.zip?context=bWFzdGVyfHJvb3R8MjM5NzQxMXxhcHBsaWNhdGlvbi96aXB8aGYxL2g5YS85NDMyNzcxMTMzNDcwLnppcHxlMTA1NmYzODFjYmJmNzhhYTZhNDRjYWM3OGE3NDc5YjhiZjA4NzhmNDI4NWY3NWE4YmFkYjhiYzkyMDEzMmJm",
 "exemptions":"https://mr.gov.il/ilgstorefront/medias/Exemptions-01112026.zip?context=bWFzdGVyfHJvb3R8MjYyOTIzNTB8YXBwbGljYXRpb24vemlwfGgzYy9oYWIvOTQzMjc3MTg1NDM2Ni56aXB8ZWNjMDlkNjgyZGQ5MTMxZTdhYmQ2OTY5YTlhZDc4MjExZGZmYjEwZDRhYjcyMjNkYWRjZDRlMzk5YTgwMjQ0Mg"
}
def scan():
 result={"checked_at":datetime.now(timezone.utc).isoformat(),"source_page":"https://mr.gov.il/ilgstorefront/he/news/details/230920201036","files":{}}
 for name,url in FILES.items():
  row={"url":url}
  try:
   req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; Rosario-public-audit/1.0)","Accept":"application/zip,*/*"})
   with urlopen(req,timeout=45) as res:
    raw=res.read(80_000_000)
    row.update(http=res.status,bytes=len(raw),content_type=res.headers.get("Content-Type"),final_url=res.geturl())
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    row["entries"]=[{"name":x.filename,"uncompressed_bytes":x.file_size,"compressed_bytes":x.compress_size} for x in z.infolist()]
    row["zip_valid"]=True
  except (HTTPError,URLError,TimeoutError,OSError,zipfile.BadZipFile) as exc:
   row["error"]=type(exc).__name__+": "+str(exc)[:220]
  result["files"][name]=row
  print(name,json.dumps(row,ensure_ascii=False),flush=True)
 Path("monthly_procurement_probe.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":scan()
