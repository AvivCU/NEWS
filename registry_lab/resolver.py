"""Read-only company registry lookup; no network or CRM side effects."""
import argparse, csv, difflib, json, os, re, sqlite3, unicodedata
from pathlib import Path
from contextlib import closing

SCHEMA = 1

def normalize(s):
    s = unicodedata.normalize('NFKC', s).casefold()
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'(?<!\w)בע["׳״\'~]?מ\s*$', '', s)
    s = re.sub(r'\b(?:ltd|limited)\.?\s*$', '', s)
    return ' '.join(re.findall(r'[^\W_]+', s))

def valid_id(s):
    return bool(re.fullmatch(r'[0-9]{9}', s)) and sum(sum(map(int,str(int(c)*(1+i%2)))) for i,c in enumerate(s)) % 10 == 0

def build(inputs, destination, expected=None):
    destination = Path(destination)
    temp = destination.with_name(destination.name + '.building')
    if temp.exists():
        raise FileExistsError(temp)
    try:
        with closing(sqlite3.connect(temp)) as db:
            db.executescript('''PRAGMA user_version=1;
            CREATE TABLE companies(id TEXT PRIMARY KEY, he TEXT, en TEXT, status TEXT, kind TEXT, city TEXT) WITHOUT ROWID;
            CREATE TABLE names(name TEXT, id TEXT, PRIMARY KEY(name,id)) WITHOUT ROWID;''')
            invalid = 0
            for path in inputs: # first input wins; all aliases retained
                with open(path, encoding='utf-8-sig', newline='') as f:
                    for row in csv.DictReader(f):
                        cid = row['מספר חברה'].strip()
                        if not valid_id(cid):
                            invalid += 1
                            continue
                        he,en = row['שם חברה'],row['שם באנגלית']
                        db.execute('INSERT OR IGNORE INTO companies VALUES(?,?,?,?,?,?)',(cid,he,en,row['סטטוס חברה'],row['סוג תאגיד'],row['שם עיר']))
                        db.executemany('INSERT OR IGNORE INTO names VALUES(?,?)',[(n,cid) for n in {normalize(he),normalize(en)} if n])
                db.commit()
            count = db.execute('SELECT count(*) FROM companies').fetchone()[0]
            if not count or (expected is not None and expected != count) or db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('Registry count/integrity mismatch')
        os.replace(temp,destination)
        return {'companies':count,'invalid_rows':invalid}
    finally:
        temp.unlink(missing_ok=True)

def connect(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    if db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA:
        db.close()
        raise ValueError('Unsupported schema')
    return db

def resolve(db, query):
    query = query.strip()
    if re.fullmatch(r'[0-9]+',query):
        row = db.execute('SELECT * FROM companies WHERE id=?',(query,)).fetchone() if valid_id(query) else None
        return {'status':'exact' if row else 'missing','candidates':[dict(row)] if row else []}
    name = normalize(query)
    if len(name)<4:
        return {'status':'too_short','candidates':[]}
    exact = db.execute('SELECT c.* FROM names n JOIN companies c ON c.id=n.id WHERE n.name=? LIMIT 6',(name,)).fetchall()
    if exact:
        return {'status':'exact' if len(exact)==1 else 'ambiguous','candidates':[dict(r) for r in exact[:5]]}
    prefix = name[:5]
    rows = db.execute('SELECT name,id FROM names WHERE name>=? AND name<? LIMIT 101',(prefix,prefix+chr(0x10ffff))).fetchall()
    if len(rows)>100:
        return {'status':'too_broad','candidates':[]}
    ranked = {}
    for r in rows:
        score = difflib.SequenceMatcher(None,name,r['name']).ratio()
        if score>=.65:
            ranked[r['id']] = max(score,ranked.get(r['id'],0))
    ids = sorted(ranked,key=lambda i:(-ranked[i],i))[:5]
    return {'status':'review' if ids else 'missing','candidates':[dict(db.execute('SELECT * FROM companies WHERE id=?',(i,)).fetchone()) for i in ids]}

if __name__=='__main__':
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build'); b.add_argument('db'); b.add_argument('inputs',nargs='+'); b.add_argument('--expected',type=int)
    q=sub.add_parser('query'); q.add_argument('db'); q.add_argument('name')
    a=p.parse_args()
    if a.command=='build':
        print(json.dumps(build(a.inputs,a.db,a.expected)))
    else:
        with closing(connect(a.db)) as db:
            print(json.dumps(resolve(db,a.name),ensure_ascii=False))
