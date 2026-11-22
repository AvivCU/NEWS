import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import daily_procurement as p
class MonitorTests(unittest.TestCase):
 def test_links(self):
  h='<a href="/ilgstorefront/medias/Tenders-01112026.zip?context=ABC">T</a><a href="/ilgstorefront/medias/Exemptions-01112026.zip?context=XYZ">E</a>'
  self.assertEqual(set(p.extract(h)),{"tenders","exemptions"})
 def test_latest(self):
  h='/ilgstorefront/medias/Tenders-01102026.zip /ilgstorefront/medias/Tenders-01112026.zip?context=XXX'
  self.assertIn("context=XXX",p.extract(h)["tenders"])
 def test_missing_page_never_updates_state(self):
  with tempfile.TemporaryDirectory() as d:
   with patch.object(p,"STATE",Path(d)/"s.json"),patch.object(p,"REPORT",Path(d)/"r.json"),patch.object(p,"listing",return_value={"bytes":5,"links":{}}):
    self.assertEqual(p.run()["outcome"],"failed")
    self.assertFalse(p.STATE.exists())
if __name__=="__main__":unittest.main()
