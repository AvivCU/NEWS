"""Inspect official monthly XLS schema and small row samples only; does not publish raw files."""
import json, tempfile, zipfile, os, gc
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from monthly_procurement_probe import FILES

def run():
 import xlrd
 result={"utc":datetime.now(timezone.utc).isoformat(),"files":{}}
 for kind,url in FILES.items():
  info={"url":url}
  try:
   with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"archive.zip"
    req=Request(url,headers={"User-Agent":"Rosario-Feeds-schema-audit/1.0","Accept":"application/zip"})
    with urlopen(req,timeout=90) as r, p.open("wb") as w:
     while True:
      b=r.read(1048576)
      if not b:break
      w.write(b)
    with zipfile.ZipFile(p) as z:
     member=next(x for x in z.infolist() if x.filename.lower().endswith(".xls"))
     extracted=Path(td)/"source.xls"
     with z.open(member) as source,extracted.open("wb") as target:
      import shutil
      shutil.copyfileobj(source,target,1048576)
    del p
    print(kind,"XLS_MB",round(extracted.stat().st_size/1e6,1),flush=True)
    book=xlrd.open_workbook(str(extracted),on_demand=True,ragged_rows=True)
    info["sheets"]=[]
    for name in book.sheet_names():
     sheet=book.sheet_by_name(name)
     s={"name":name,"nrows":sheet.nrows,"ncols":sheet.ncols,"head":[[str(x)[:160] for x in sheet.row_values(i)[:60]] for i in range(min(5,sheet.nrows))]}
     info["sheets"].append(s)
     print(kind,"SHEET",name,sheet.nrows,sheet.ncols,"HEAD",json.dumps(s["head"][:3],ensure_ascii=False)[:3500],flush=True)
     book.unload_sheet(name)
    book.release_resources()
  except Exception as e:
   info["error"]=repr(e)[:300];print(kind,"ERROR",repr(e),flush=True)
  result["files"][kind]=info
 Path("monthly_schema.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":run()
