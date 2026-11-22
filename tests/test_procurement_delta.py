import gzip,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import procurement_delta as d

N='urn:schemas-microsoft-com:office:spreadsheet'
HEAD=['מספר פרסום','שם הליך','סטטוס','שם ספק זוכה','מספר חפ ספק','תאריך פרסום','תאריך עדכון','שם המשרד']
def make(path,rows):
 lines=['<?xml version="1.0" encoding="UTF-8"?>','<Workbook xmlns:ss="'+N+'" xmlns="'+N+'"><Worksheet ss:Name="Test"><Table>']
 for r in [HEAD]+rows:
  lines.append('<Row>'+''.join('<Cell><Data>'+v.replace('&','&amp;').replace('<','&lt;')+'</Data></Cell>' for v in r)+'</Row>')
 lines.append('</Table></Worksheet></Workbook>')
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('test.xls',''.join(lines))
class DeltaTests(unittest.TestCase):
 def test_new_winner_status_and_no_duplicates(self):
  with tempfile.TemporaryDirectory() as tmp:
   old=Path(tmp)/'old.zip';new=Path(tmp)/'new.zip';dest=Path(tmp)/'next.json.gz'
   make(old,[['101','מכרז א','פתוח','','','01.11.2026','01.11.2026','משרד א']])
   make(new,[['101','מכרז א','סגור','חברה בעמ','12345','01.11.2026','20.11.2026','משרד א'],
             ['102','מכרז ב','פתוח','','','22.11.2026','22.11.2026','משרד ב']])
   with patch.object(d,'SNAPSHOTS',Path(tmp)):
    baseline=d.prepare(old,'tenders',dest)
    self.assertEqual(baseline['status'],'baseline')
    dest.replace(Path(tmp)/'tenders.json.gz')
    delta=d.prepare(new,'tenders',dest)
    self.assertEqual(delta['counts']['new_publication'],1)
    self.assertEqual(delta['counts']['winner_assigned'],1)
    self.assertEqual(delta['counts']['status_changed'],1)
    dest.replace(Path(tmp)/'tenders.json.gz')
    again=d.prepare(new,'tenders',dest)
    self.assertEqual(sum(again['counts'].values()),0)
 def test_only_update_date_does_not_trigger(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'a.zip';q=Path(tmp)/'b.zip';t=Path(tmp)/'next.json.gz'
   make(p,[['100','מכרז','פתוח','','','01.11.2026','01.11.2026','משרד']])
   make(q,[['100','מכרז','פתוח','','','01.11.2026','02.11.2026','משרד']])
   with patch.object(d,'SNAPSHOTS',Path(tmp)):
    d.prepare(p,'tenders',t);t.replace(Path(tmp)/'tenders.json.gz')
    x=d.prepare(q,'tenders',t)
    self.assertEqual(sum(x['counts'].values()),0)
 def test_strange_spreadsheet_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'bad.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('wrong.xls','<Workbook><Row><Cell>unrecognized</Cell></Row></Workbook>')
   with self.assertRaises(ValueError):d.index_archive(p,'tenders')
if __name__=='__main__':unittest.main()
