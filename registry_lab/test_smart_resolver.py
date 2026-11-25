import sqlite3
import unittest
from smart_resolver import resolve_smart, variants, MAX_ROWS, MAX_QUERIES

class SmartTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:'); self.addCleanup(self.db.close); self.db.row_factory=sqlite3.Row
        self.db.executescript('CREATE TABLE companies(id TEXT PRIMARY KEY, he TEXT, en TEXT, status TEXT, kind TEXT, city TEXT) WITHOUT ROWID; CREATE TABLE names(name TEXT,id TEXT,PRIMARY KEY(name,id)) WITHOUT ROWID;')
        from resolver import normalize
        self.add=lambda cid,n: (self.db.execute('INSERT OR IGNORE INTO companies VALUES(?,?,?,?,?,?)',(cid,n,'','TEST','TEST','')),self.db.execute('INSERT INTO names VALUES(?,?)',(normalize(n),cid)))
        for cid,n in [('a','א.ב. שקדונים בע"מ'),('b','א.ב. שקדונים יזמות בע"מ'),('c','קבוצת בית נחליאלי שלי בע"מ'),('d','בית נחליאלי שלי נכסים בע"מ'),('e','בית נחליאלי שלי יזמות בע"מ'),('f','קיי.טי.וי תכלת בע"מ'),('g','מיני טקסט בע"מ'),('h','מגדל דוגמה 1999 בע"מ'),('i','מגדל דוגמה 2000 בע"מ'),('j','דלת אלפא בע"מ'),('k','דלת אלפא בע"מ'),('l','Alpha Mock Ltd'),('m','סופר פטל בע"מ'),('n','ספק פיקטיבי בע"מ')]: self.add(cid,n)
    def query(self,q,aliases=()):return resolve_smart(self.db,q,aliases)
    def ids(self,q,aliases=()):return [r['id'] for r in self.query(q,aliases)['candidates']]
    def test_owner_annotation(self):
        r=self.query('א.ב. שקדונים (שם בעלים)');self.assertEqual(r['status'],'review');self.assertEqual(r['candidates'][0]['id'],'a')
    def test_group_label(self): self.assertEqual(self.ids('קבוצת בית נחליאלי (BN)')[0],'c')
    def test_reversed_brackets_transposition(self): self.assertIn('c',self.ids('קבוצות יבת נחליאלי )BN('))
    def test_group_not_approved(self): self.assertEqual(self.query('קבוצת בית נחליאלי')['status'],'review')
    def test_acronym(self): self.assertIn('f',self.ids('KTV תכלת (תחום הדוגמה)'))
    def test_split_word(self): self.assertIn('g',self.ids('מיניטקסט (תחום הדוגמה)'))
    def test_year_kept(self): self.assertEqual(self.ids('מגדל דוגמה (1999)')[0],'h')
    def test_duplicate(self): self.assertEqual(self.query('דלת אלפא')['status'],'ambiguous')
    def test_alias(self): self.assertIn('n',self.ids('מותג לא רשום',['ספק פיקטיבי']))
    def test_bilingual_annotation(self): self.assertIn('l',self.ids('שם מותג (Alpha Mock)'))
    def test_exact(self): self.assertEqual(self.query('סופר פטל בע"מ')['status'],'exact')
    def test_missing(self): self.assertFalse(self.ids('זזזזזזזזז'))
    def test_broad_cap(self):
        for i in range(150):self.add('z'+str(i),'קבוצת פיקטיביה '+str(i))
        r=self.query('קבוצת פיקטיביה');self.assertFalse(r['candidates']);self.assertTrue(r['truncated']);self.assertLessEqual(r['rows_examined'],MAX_ROWS);self.assertLessEqual(r['queries'],MAX_QUERIES)
    def test_not_sql_injection(self):self.assertFalse(self.ids("x'; DROP TABLE names; --"));self.assertGreater(self.db.execute('SELECT count(*) FROM names').fetchone()[0],0)
    def test_long_query(self):self.assertEqual(self.query('א'*513)['status'],'too_long')
    def test_query_plan(self):
        plan=self.db.execute('EXPLAIN QUERY PLAN SELECT name,id FROM names WHERE name>=? AND name<? LIMIT ?',('a','b',26)).fetchall();self.assertTrue(any('SEARCH' in r[3] for r in plan))

if __name__=='__main__': unittest.main()
