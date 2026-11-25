"""Schema-1 bounded typo recovery; all new matches are review-only."""
import re
from smart_resolver import resolve_smart, variants
from resolver import normalize

MAX_KEYS = 6000
MAX_ROWS = 200
BATCH = 300
MAX_SEEDS = 3
MAX_SEED_LENGTH = 64
MAX_PREFIX_PROBES = 700
MAX_PREFIX_ROWS = 256
HE = 'אבגדהוזחטיכלמנסעפצקרשתךםןףץ'
EN = 'abcdefghijklmnopqrstuvwxyz'


def edit_keys(seed):
    """One edit, adjacent transposition, space insertion/deletion, word swap.
    Numeric characters are preserved. No exhaustive edit-distance scan."""
    alphabet = HE if re.search('[א-ת]',seed) else EN
    for i,c in enumerate(seed):
        if c.isalpha() or c==' ':
            yield seed[:i]+seed[i+1:], 'delete'
        if i+1<len(seed) and c.isalpha() and seed[i+1].isalpha() and c!=seed[i+1]:
            yield seed[:i]+seed[i+1]+c+seed[i+2:], 'transpose'
        if c in alphabet:
            for x in alphabet:
                if x!=c: yield seed[:i]+x+seed[i+1:], 'substitute'
        if c.isalpha():
            for x in alphabet:
                yield seed[:i]+x+seed[i:], 'insert'
            if i and seed[i-1].isalpha(): yield seed[:i]+' '+seed[i:], 'split'
    if seed[-1].isalpha():
        for x in alphabet: yield seed+x,'insert'
    tokens=seed.split()
    for i in range(len(tokens)-1):
        t=tokens[:];t[i],t[i+1]=t[i+1],t[i]
        yield ' '.join(t),'word_swap'


def distance_at_most_two(a,b):
    if abs(len(a)-len(b))>2 or re.findall(r'\d+',a)!=re.findall(r'\d+',b): return 3
    prev2={}; prev={j:j for j in range(min(2,len(b))+1)}
    for i,ca in enumerate(a,1):
        cur={0:i} if i<=2 else {}
        for j in range(max(1,i-2),min(len(b),i+2)+1):
            cur[j]=min(prev.get(j,3)+1,cur.get(j-1,3)+1,prev.get(j-1,3)+(ca!=b[j-1]))
            if i>=2 and j>=2 and ca==b[j-2] and a[i-2]==b[j-1]:cur[j]=min(cur[j],prev2.get(j-2,3)+1)
        prev2,prev=prev,cur
    return min(3,prev.get(len(b),3))


def resolve_robust(db, query, aliases=()):
    base=resolve_smart(db,query,aliases)
    if base['status'] in {'exact','ambiguous','too_long'} or re.fullmatch(r'[0-9]+',query.strip()):
        return base
    seeds=variants(query,aliases)
    # The annotated original is often unsuitable for edits; prioritize cleaned names.
    seeds=[(s,m,w) for s,(m,w) in seeds.items() if 5<=len(s)<=MAX_SEED_LENGTH and m not in {'with_group','transliterated_acronym','spaced_acronym','bilingual_annotation'} and (sum(c.isalpha() for c in s)>=5)]
    seeds.sort(key=lambda x:(x[1]!='without_annotation' if '(' in query or ')' in query else False,-x[2]))
    # Preserve strong clean prefix or spacing matches already found by V2.
    if base['candidates']:
        best=base['candidates'][0]; matched=best.get('matched_name','')
        if any(matched==s or matched.startswith(s+' ') or matched.replace(' ','')==s.replace(' ','') for s,_,_ in seeds):
            return base
    keys={}; truncated=False
    for s,m,w in seeds[:MAX_SEEDS]:
        for key,edit in edit_keys(s):
            if len(keys)>=MAX_KEYS:
                truncated=True; break
            if key==s or not key or key.strip()!=key or '  ' in key:continue
            score=w*(.94 if edit in {'transpose','word_swap','split'} else .91)
            if key not in keys or keys[key][0]<score: keys[key]=(score,edit,s)
        if truncated:break
    ranked={c['id']:dict(c) for c in base['candidates']}
    rows_seen=0; batches=0
    all_keys=list(keys)
    for i in range(0,len(all_keys),BATCH):
        part=all_keys[i:i+BATCH]; rem=MAX_ROWS-rows_seen
        if rem<=0:truncated=True;break
        rows=db.execute('SELECT name,id FROM names WHERE name IN ('+','.join('?' for _ in part)+') LIMIT ?',(*part,rem+1)).fetchall();batches+=1
        if len(rows)>rem:
            truncated=True;break  # do not rank a partial result set
        rows_seen+=len(rows)
        for r in rows:
            score,edit,seed=keys[r['name']]; cid=r['id']
            if cid not in ranked or score>ranked[cid].get('score',0):
                ranked[cid]={'id':cid,'score':score,'match_method':'edit_'+edit,'matched_name':r['name'],'seed':seed}
    prefix_probes=0; prefix_rows=0
    # Correct a leading token, then verify the full string with distance <=2.
    if not any(c.get('score',0)>=.80 for c in ranked.values()):
        for seed,_,w in seeds[:1]:
            ts=seed.split()
            if len(ts)<2 or not 4<=len(ts[0])<=12 or not ts[0].isalpha():continue
            anchors={ts[0],*(k for k,_ in edit_keys(ts[0]) if k.isalpha() and len(k)>=4)}
            for anchor in sorted(anchors,key=lambda k:(k!=ts[0], k)):
                if prefix_probes>=MAX_PREFIX_PROBES or prefix_rows>=MAX_PREFIX_ROWS: truncated=True;break
                limit=min(13,MAX_PREFIX_ROWS-prefix_rows)
                key=anchor+' ';prefix_probes+=1
                rows=db.execute('SELECT name,id FROM names WHERE name>=? AND name<? LIMIT ?',(key,key+chr(0x10ffff),limit)).fetchall();prefix_rows+=len(rows)
                if len(rows)>=limit:truncated=True;continue
                for r in rows:
                    d=distance_at_most_two(seed,r['name'])
                    if d>2:continue
                    score=w*(.87 if d==1 else .80);cid=r['id']
                    if cid not in ranked or score>ranked[cid].get('score',0):
                        ranked[cid]={'id':cid,'score':score,'match_method':'bounded_prefix_edit','matched_name':r['name'],'seed':seed}
    candidates=[]
    for cid,r in sorted(ranked.items(),key=lambda x:(-x[1].get('score',0), x[0]))[:5]:
        if 'he' not in r:r=dict(db.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone())|r
        r['score']=round(r.get('score',0),3);candidates.append(r)
    return {**base,'status':'review' if candidates else ('too_broad' if truncated else base['status']), 'candidates':candidates,'edit_keys':len(keys),'edit_batches':batches,'edit_rows':rows_seen,'prefix_probes':prefix_probes,'prefix_rows':prefix_rows,'truncated':base.get('truncated',False) or truncated}
