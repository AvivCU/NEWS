import csv, gzip, shutil, sqlite3, tempfile, unittest
from pathlib import Path
from contextlib import closing
from resolver import build,connect,resolve,valid_id
from storage import ensure,digest

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.ids=[str(i) for i in range(510000000,510000100) if valid_id(str(i))][:4]
        headers=['מספר חברה','שם חברה','שם באנגלית','סטטוס חברה','סוג תאגיד','שם עיר']
        for fn, rows in [('main.csv',[(self.ids[0],'אלפא דוגמה בע~מ','Alpha Example Ltd'),(self.ids[1],'בטא דוגמה','Beta Example'),(self.ids[2],'בטא דוגמה','Beta Two')]),('append.csv',[(self.ids[0],'אלפא היסטורית','Alpha Old')])]:
            with open(self.root/fn,'w',encoding='utf-8',newline='') as f:
                w=csv.writer(f); w.writerow(headers)
                for row in rows: w.writerow((*row,'פעילה','פרטית',''))
        self.db=self.root/'db.sqlite'; self.inputs=[self.root/'main.csv',self.root/'append.csv']; build(self.inputs,self.db,3)
    def query(self,q):
        with closing(connect(self.db)) as db: return resolve(db,q)
    def test_id(self): self.assertEqual(self.query(self.ids[0])['status'],'exact')
    def test_hebrew(self): self.assertEqual(self.query('אלפא דוגמה בע״מ')['candidates'][0]['id'],self.ids[0])
    def test_english(self): self.assertEqual(self.query('ALPHA EXAMPLE LIMITED')['status'],'exact')
    def test_alias(self): self.assertEqual(self.query('Alpha Old')['candidates'][0]['he'],'אלפא דוגמה בע~מ')
    def test_ambiguity(self): self.assertEqual(self.query('בטא דוגמה')['status'],'ambiguous')
    def test_fuzzy(self): self.assertEqual(self.query('Alpha Exampel')['status'],'review')
    def test_missing(self): self.assertEqual(self.query('zzzzz missing')['status'],'missing')
    def test_injection(self): self.assertEqual(self.query("x'; drop table companies; --")['status'],'missing')
    def test_invalid_id(self): self.assertEqual(self.query('123')['status'],'missing')
    def test_failed_build_preserves(self):
        before=digest(self.db)
        with self.assertRaises(ValueError): build(self.inputs,self.db,4)
        self.assertEqual(before,digest(self.db))
    def test_missing_db(self):
        with self.assertRaises(sqlite3.OperationalError): connect(self.root/'missing')
    def test_storage(self):
        gz=self.root/'release.gz'
        with open(self.db,'rb') as src,gzip.open(gz,'wb') as dst: shutil.copyfileobj(src,dst)
        m={'tag':'synthetic-v1','repo':'example/lab','asset':'db.gz','db_sha256':digest(self.db),'asset_sha256':digest(gz),'db_bytes':self.db.stat().st_size,'count':3}
        dest=self.root/'restored.sqlite'
        def download(_,p): shutil.copyfile(gz,p)
        self.assertEqual(ensure(m,dest,download),'restored')
        self.assertEqual(ensure(m,dest,lambda *_: self.fail('cache should hit')),'cache_hit')
        with self.assertRaises(ValueError): ensure(dict(m,asset_sha256='0'*64,db_sha256='0'*64),dest,download)
        self.assertEqual(digest(dest),m['db_sha256'])

if __name__=='__main__': unittest.main()
