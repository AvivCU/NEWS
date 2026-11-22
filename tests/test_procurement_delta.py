import gzip,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import procurement_delta as d

N='urn:schemas-microsoft-com:office:spreadsheet'
HEAD=['מספר פרסום','שם הליך','סטטוס','שם ספק זוכה','מספר חפ ספק','תאריך פרסום','תאריך עדכון','שם המשרד','היקף כספי','מטבע','תאריך תחילת תקופת התקשרות','תאריך סיום תקופת התקשרות']
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

 def test_old_tender_winner_is_new_event_today(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'old.zip';q=Path(tmp)/'new.zip';out=Path(tmp)/'next.json.gz'
   make(p,[['450','מכרז ישן','פתוח','','','12.01.2025','12.01.2025','משרד']])
   make(q,[['450','מכרז ישן','סגור','ספק חדש','512345678','12.01.2025','21.11.2026','משרד']])
   with patch.object(d,'SNAPSHOTS',Path(tmp)):
    d.prepare(p,'tenders',out);out.replace(Path(tmp)/'tenders.json.gz')
    result=d.prepare(q,'tenders',out)
    self.assertEqual(result['counts']['winner_assigned'],1)
    self.assertEqual(result['recent_counts']['winner_assigned'],1)
    self.assertEqual(len(result['events']),1)
    self.assertEqual(result['events'][0]['detected_utc'][:4],'2026')
    self.assertFalse(result['events'][0]['historical_backfill'])
 def test_amount_and_contract_period_are_material_events(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'old.zip';q=Path(tmp)/'new.zip';out=Path(tmp)/'next.json.gz'
   start=['900','פטור לחברה','מאושר','חברה בעמ','512345678','03.05.2023','15.11.2026','משרד']
   make(p,[start+['10,000,000.00','ILS','01.01.2024','31.12.2026']])
   make(q,[start+['50,000,000','ILS','01.01.2024','31.12.2028']])
   with patch.object(d,'SNAPSHOTS',Path(tmp)):
    d.prepare(p,'exemptions',out);out.replace(Path(tmp)/'exemptions.json.gz')
    result=d.prepare(q,'exemptions',out)
    self.assertEqual(result['counts']['amount_changed'],1)
    self.assertEqual(result['counts']['period_changed'],1)
    self.assertEqual(result['recent_counts']['amount_changed'],1)
    self.assertEqual(result['recent_counts']['period_changed'],1)
    event=result['events'][0]
    self.assertEqual(set(event['change_types']),{'amount_changed','period_changed'})
    self.assertIn('10000000 ILS',event['financial_before']['amounts'])
    self.assertIn('50000000 ILS',event['financial_after']['amounts'])
    self.assertIn('2024-01-01 → 2028-12-31',event['financial_after']['periods'])
 def test_amount_format_only_does_not_alert(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'old.zip';q=Path(tmp)/'new.zip';out=Path(tmp)/'next.json.gz'
   start=['900','פטור','מאושר','חברה','512345678','03.05.2023','15.11.2026','משרד']
   make(p,[start+['1,000.00','ILS','01.01.2024','31.12.2026']])
   make(q,[start+['1000','ILS','2024-01-01','2026-12-31']])
   with patch.object(d,'SNAPSHOTS',Path(tmp)):
    d.prepare(p,'exemptions',out);out.replace(Path(tmp)/'exemptions.json.gz')
    result=d.prepare(q,'exemptions',out)
    self.assertEqual(result['counts']['amount_changed'],0)
    self.assertEqual(result['counts']['period_changed'],0)
    self.assertEqual(result['events'],[])
 def test_legacy_baseline_migrates_without_false_financial_alert(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'old.zip';out=Path(tmp)/'next.json.gz'
   base=['900','פטור','מאושר','חברה','512345678','03.05.2023','15.11.2026','משרד']
   make(p,[base+['1000','ILS','01.01.2024','31.12.2026']])
   old=d.index_archive(p,'exemptions')
   old['schema']=1
   for item in old['items'].values():item.pop('financial',None)
   with patch.object(d,'SNAPSHOTS',Path(tmp)):
    with gzip.open(Path(tmp)/'exemptions.json.gz','wt',encoding='utf8') as f:json.dump(old,f)
    result=d.prepare(p,'exemptions',out)
    self.assertEqual(result['events'],[])
    self.assertEqual(sum(result['counts'].values()),0)
    with gzip.open(out,'rt',encoding='utf8') as f:self.assertEqual(json.load(f)['schema'],2)

if __name__=='__main__':unittest.main()
