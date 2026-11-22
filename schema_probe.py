"""Streaming XML Spreadsheet 2003 schema inspector for official government reports."""
import json,tempfile,zipfile,shutil
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from xml.etree.ElementTree import iterparse
from monthly_procurement_probe import FILES

NS="{urn:schemas-microsoft-com:office:spreadsheet}"
def inspect(path,max_head=5):
 sheets=[]; current=None;row=[];count=0
 for event,elem in iterparse(path,events=("start","end")):
  name=elem.tag.rsplit("}",1)[-1]
  if event=="start" and name=="Worksheet":
   current={"name":elem.attrib.get(NS+"Name"),"rows":0,"head":[]};sheets.append(current)
  elif event=="end" and name=="Row":
   if current is not None:
    current["rows"]+=1
    if len(current["head"])<max_head:
     vals=[]
     for cell in elem:
      if cell.tag.rsplit("}",1)[-1]!="Cell":continue
      index=cell.attrib.get(NS+"Index")
      if index and index.isdigit():
       idx=int(index)-1
       while len(vals)<min(idx,100):vals.append("")
      value=next((x.text or "" for x in cell if x.tag.rsplit("}",1)[-1]=="Data"),"")
      if len(vals)<100:vals.append(str(value)[:150])
     current["head"].append(vals)
   elem.clear()
  elif event=="end" and name=="Worksheet":elem.clear()
 return sheets
def run():
 out={"utc":datetime.now(timezone.utc).isoformat(),"files":{}}
 for kind,url in FILES.items():
  info={}
  try:
   with tempfile.TemporaryDirectory() as td:
    zp=Path(td)/"data.zip"
    with urlopen(Request(url,headers={"User-Agent":"RosarioPublicFeedSchema/1.0"}),timeout=90) as r,zp.open("wb") as f:
     shutil.copyfileobj(r,f,1024*1024)
    with zipfile.ZipFile(zp) as z:
     m=next(x for x in z.infolist() if x.filename.lower().endswith(".xls"))
     p=Path(td)/"data.xls"
     with z.open(m) as f,p.open("wb") as target:shutil.copyfileobj(f,target,1024*1024)
    info["xls_size"]=p.stat().st_size
    info["sheets"]=inspect(p)
    for sh in info["sheets"]:
     print(kind,"ROWS",sh["rows"],"HEAD",json.dumps(sh["head"][:3],ensure_ascii=False)[:3800],flush=True)
  except Exception as e:info["error"]=repr(e)[:400];print(kind,"ERROR",repr(e),flush=True)
  out["files"][kind]=info
 Path("monthly_schema.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":run()
