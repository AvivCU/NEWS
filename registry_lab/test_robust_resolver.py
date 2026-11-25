import sqlite3
import unittest
from resolver import normalize
from robust_resolver import (resolve_robust, distance_at_most_two, MAX_KEYS, MAX_ROWS, MAX_PREFIX_PROBES, MAX_PREFIX_ROWS)


class RobustTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:'); self.addCleanup(self.db.close); self.db.row_factory=sqlite3.Row
        self.db.executescript('CREATE TABLE companies(id TEXT PRIMARY KEY, he TEXT, en TEXT, status TEXT, kind TEXT, city TEXT) WITHOUT ROWID; CREATE TABLE names(name TEXT,id TEXT,PRIMARY KEY(name,id)) WITHOUT ROWID;')
        for cid,name in [('a','שקדונים תכלת'),('b','סיגמא ירוקה'),('c','Alpha Example'),('d','שקדונים פרויקטים'),('e','דוגמה ייחודית 1999'),('f','קבוצת דלת ברקת'),('g','קבוצת דלת ברקת'),('h','מיניליין דוגמה')]:self.add(cid,name)
    def add(self,cid,name):
        self.db.execute('INSERT INTO companies VALUES(?,?,?,?,?,?)',(cid,name,'','TEST','TEST',''))
        self.db.execute('INSERT INTO names VALUES(?,?)',(normalize(name),cid))
    def find(self,q):return resolve_robust(self.db,q)
    def assert_candidate(self,q,cid):
        r=self.find(q);self.assertIn(cid,[x['id'] for x in r['candidates']]);self.assertEqual(r['status'],'review');return r
    def test_first_letter(self):self.assert_candidate('זק דונים תכלת'.replace(' ','',1),'a')
    def test_missing_first(self):self.assert_candidate('קדונים תכלת','a')
    def test_extra_first(self):self.assert_candidate('זשקדונים תכלת','a')
    def test_middle(self):self.assert_candidate('שקדונים תכחת','a')
    def test_transposition(self):self.assert_candidate('קשדונים תכלת','a')
    def test_space(self):self.assert_candidate('שקדוניםתכלת','a')
    def test_reorder(self):self.assert_candidate('תכלת שקדונים','a')
    def test_owner_annotation(self):self.assert_candidate('זק דונים תכלת (שם בעלים)'.replace(' ','',1),'a')
    def test_english(self):self.assert_candidate('Xlpha Example','c')
    def test_two_errors(self):self.assert_candidate('זקדונים תכלמ','a')
    def test_exact_preserved(self):self.assertEqual(self.find('שקדונים תכלת')['status'],'exact')
    def test_duplicate_preserved(self):self.assertEqual(self.find('קבוצת דלת ברקת')['status'],'ambiguous')
    def test_clean_prefix_preserved(self):self.assertEqual(self.find('מיניליין (תיאור פעילות)')['candidates'][0]['id'],'h')
    def test_numeric_identity(self):self.assertNotIn('e',[x['id'] for x in self.find('דוגמה ייחודית 1998')['candidates'] if x.get('match_method','').startswith(('edit_','bounded_prefix'))])
    def test_distance(self):
        for a,b,d in [('abc','abc',0),('abc','bac',1),('abc','ab',1),('abc','xbc',1),('abc','xbcx',2),('abc','xyz',3),('abc 1998','abc 1999',3)]:self.assertEqual(distance_at_most_two(a,b),d)
    def test_bounds(self):
        r=self.find('זקדונים תכלמ');self.assertLessEqual(r.get('edit_keys',0),MAX_KEYS);self.assertLessEqual(r.get('edit_rows',0),MAX_ROWS);self.assertLessEqual(r.get('prefix_probes',0),MAX_PREFIX_PROBES);self.assertLessEqual(r.get('prefix_rows',0),MAX_PREFIX_ROWS);self.assertLessEqual(len(r['candidates']),5)
    def test_unknown(self):self.assertNotEqual(self.find('זזזזזזזזזז זזזזזזזז')['status'],'exact')
    def test_plan(self):
        for sql,args in [('SELECT name,id FROM names WHERE name IN (?,?) LIMIT ?',('a','b',10)),('SELECT name,id FROM names WHERE name>=? AND name<? LIMIT ?',('a','b',10))]:
            plan=self.db.execute('EXPLAIN QUERY PLAN '+sql,args).fetchall();self.assertTrue(any('SEARCH' in row[3] for row in plan));self.assertFalse(any('SCAN' in row[3] for row in plan))

if __name__=='__main__':unittest.main()
