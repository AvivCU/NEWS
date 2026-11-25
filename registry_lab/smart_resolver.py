"""Bounded CRM-label lookup on schema 1. Only the original exact key can be exact."""
import difflib
import re
from resolver import normalize, resolve as basic_resolve

MAX_ROWS = 100
MAX_QUERIES = 32
MAX_VARIANTS = 12
GROUP = {'קבוצת', 'קבוצות', 'קבוצה', 'group', 'גרופ'}
LETTERS = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ', ['איי','בי','סי','די','אי','אף','גי','אייץ','איי','גי','קיי','אל','אם','אן','או','פי','קיו','אר','אס','טי','יו','וי','דבליו','אקס','וואי','זד']))


def variants(query, aliases=()):
    output = {}

    def add(text, method, weight):
        n = normalize(text)
        if len(n) >= 3 and (any(len(t) >= 3 and t not in GROUP for t in n.split()) or len(n.split()) >= 2 and all(len(t)==1 for t in n.split())):
            if n not in output or output[n][1] < weight:
                output[n] = (method, weight)

    for i, text in enumerate((query, *tuple(aliases)[:3])):
        weight = 1 if not i else .97
        add(text, 'original' if not i else 'supplied_alias', weight)
        clean = re.sub(r'\([^()]*\)|\)[^()]*\(', ' ', text)
        if clean != text:
            add(clean, 'without_annotation', weight - .07)
        if re.search(r'\b[A-Z]{2,5}\b',clean):
            add(re.sub(r'\b[A-Z]{2,5}\b',lambda m:' '.join(m.group()),clean), 'spaced_acronym',weight-.15)
            add(re.sub(r'\b[A-Z]{2,5}\b',lambda m:' '.join(LETTERS[c] for c in m.group()),clean), 'transliterated_acronym',weight-.17)
        for part in re.split(r'\s+(?:[–—]|/|\|)\s+', clean)[:3]:
            add(part, 'label_segment', weight - .08)
            tokens = normalize(part).split()
            if tokens and tokens[0] in GROUP:
                add(' '.join(tokens[1:]), 'without_group', weight - .11)
                if tokens[0] in {'קבוצות', 'קבוצה'}:
                    add('קבוצת ' + ' '.join(tokens[1:]), 'group_variant', weight - .10)
            if tokens and tokens[0] not in GROUP and re.search('[א-ת]', part) and len(''.join(tokens)) >= 4:
                add('קבוצת ' + ' '.join(tokens), 'with_group', weight - .14)
            if tokens and tokens[-1] in GROUP:
                add(' '.join(tokens[:-1]), 'without_group', weight - .11)
            # A bilingual label may start with a brand, then a legal Hebrew name.
            he = ' '.join(t for t in tokens if re.search(r'[א-ת]', t))
            en = ' '.join(t for t in tokens if re.search('[a-z]', t))
            if he and en:
                if len(he.split()) >= 2: add(he, 'language_segment', weight - .13)
                if len(en.split()) >= 2: add(en, 'language_segment', weight - .13)
        # Parenthetical alternative in the other script, not an arbitrary owner name.
        for inner in re.findall(r'\(([^()]+)\)|\)([^()]+)\(', text):
            a = next((x for x in inner if x), '')
            if (re.search('[a-zA-Z]', a) and not re.search('[א-ת]', a) and re.search('[א-ת]', clean)) or (re.search('[א-ת]', a) and not re.search('[א-ת]', clean)):
                add(a, 'bilingual_annotation', weight - .17)
    # Expand derived variants too (e.g. bilingual label → Hebrew segment → drop group).
    for n,(m,w) in list(output.items()):
        tokens=n.split()
        if tokens and tokens[0] in GROUP:
            add(' '.join(tokens[1:]),'without_group',w-.035)
        # Joining dotted initialisms is a lookup variant, not a global normalization.
        joined=re.sub(r'(?<!\S)(?:[א-ת] ){1,4}[א-ת](?!\S)',lambda m:m.group().replace(' ',''),n)
        if joined!=n: add(joined,'joined_initials',w-.055)
    return dict(sorted(output.items(), key=lambda x:-x[1][1])[:MAX_VARIANTS])


def resolve_smart(db, query, aliases=()):
    query = query.strip()
    if len(query) > 512:
        return {'status': 'too_long', 'candidates': []}
    if re.fullmatch(r'[0-9]+', query):
        return basic_resolve(db, query)
    aliases = tuple(a[:512] for a in tuple(aliases)[:3])
    names = variants(query, aliases)
    original = normalize(query)
    context = set(original.split()) - GROUP
    found = {}; rows_seen = 0; queries = 0; truncated = False

    def result(status):
        ranked = sorted(found.items(), key=lambda x: (-x[1][0], x[0]))[:5]
        return {'status': status, 'candidates': [dict(db.execute('SELECT * FROM companies WHERE id=?', (cid,)).fetchone()) | {'match_method': v[1], 'matched_name': v[2], 'score': round(v[0], 3)} for cid, v in ranked], 'rows_examined': rows_seen, 'queries': queries, 'truncated': truncated}

    def search(key, method, weight, exact=False):
        nonlocal rows_seen, queries, truncated
        if queries >= MAX_QUERIES or rows_seen >= MAX_ROWS:
            truncated = True; return
        limit = min(26, MAX_ROWS - rows_seen)
        sql = 'SELECT name,id FROM names WHERE name=? LIMIT ?' if exact else 'SELECT name,id FROM names WHERE name>=? AND name<? LIMIT ?'
        args = (key, limit) if exact else (key, key + chr(0x10ffff), limit)
        queries += 1
        rows = db.execute(sql, args).fetchall()
        rows_seen += len(rows)
        if len(rows) >= limit:
            truncated = True
            # Do not rank an arbitrary sample from an oversized block.
            return
        for r in rows:
            n = r['name']; cid = r['id']; nt = n.split()
            if exact:
                score = weight
            else:
                score = 0
                for v, (_, w) in names.items():
                    vt = v.split(); common = (set(vt) & set(nt)) - GROUP
                    if not common and not n.startswith(key): continue
                    ratio = difflib.SequenceMatcher(None, v, n, autojunk=False).ratio()
                    coverage = len(common) / max(1, len(set(vt) - GROUP))
                    value = (.70 * ratio + .30 * coverage) * w
                    if n.startswith(v + ' '):
                        value = max(value, .88 * w - .015 * max(0, len(nt) - len(vt) - 1))
                    if 'מקבוצת' in nt and 'מקבוצת' not in vt: value -= .12
                    if set(re.findall(r'\b\d{4}\b', v)) - set(re.findall(r'\b\d{4}\b', n)): value -= .12
                    score = max(score, value)
                if method in {'transposition','split_word'}:
                    score = max(score, .76 * weight - .012 * max(0, len(nt) - len(key.split())))
                # Descriptors are soft evidence only; preserve them for ranking.
                extra = (context & set(nt)) - set(key.split())
                score += min(.09, .03 * len([t for t in extra if len(t) >= 3]))
            if score >= .46 and (cid not in found or score > found[cid][0]):
                found[cid] = (score, method, n)

    if original in names:
        search(original, 'original_exact', 1, True)
        if found or truncated: return result('exact' if len(original)>=4 and len(found)==1 and not truncated else ('review' if len(found)==1 and not truncated else 'ambiguous'))
    for n, (m, w) in names.items():
        if n != original: search(n, m, w, True)
    keys = set()

    def prefix(key, m, w):
        if key in keys or len(key) < 4: return
        keys.add(key); search(key, m, w)

    for n, (m, w) in sorted(names.items(), key=lambda x: (-len(x[0].split()), -x[1][1])):
        prefix(n + ' ', 'full_prefix', w)
    if not found:
        # Use the shortest clean variants before changing characters in long annotations.
        clean_names = sorted(((n,w) for n,(m,w) in names.items() if m not in {'original','with_group'}), key=lambda x:(len(x[0].split()),-x[1]))
        if not clean_names: clean_names = [(original,1)]
        for n,w in clean_names[:4]:
            ts=n.split()
            if not ts: continue
            idx=next((i for i,t in enumerate(ts) if t not in GROUP and len(t)>=3),None)
            if idx is None: continue
            t=ts[idx]
            if 6 <= len(t) <= 14:
                for cut in sorted(range(3,len(t)-2),key=lambda k:abs(k-len(t)/2))[:5]:
                    v=ts[:]; v[idx:idx+1]=[t[:cut],t[cut:]]
                    prefix(' '.join(v),'split_word',w-.1)
            if len(ts)>=2 and 3<=len(t)<=10:
                for i in range(len(t)-1):
                    if t[i]==t[i+1]: continue
                    v=ts[:];v[idx]=t[:i]+t[i+1]+t[i]+t[i+2:]
                    prefix(' '.join(v),'transposition',w)
                    if idx==0 and n!=original and original.split() and original.split()[0] in GROUP:
                        prefix('קבוצת '+' '.join(v),'transposition',w+.02)
            if found: break
    # Preserve baseline's partial-prefix coverage, prioritizing distinctive tokens.
    for n, (m, w) in sorted(names.items(), key=lambda x: -x[1][1]):
        tokens = n.split()
        if len(tokens) >= 3 and tokens[0] not in GROUP: prefix(' '.join(tokens[:2]) + ' ', 'two_token_prefix', w)
        if tokens and len(tokens[0]) >= 5 and tokens[0] not in GROUP:
            prefix(tokens[0][:5], 'token_prefix', w)
        if len(tokens) >= 2 and all(len(t) == 1 for t in tokens[:2]) and len(n) >= 5:
            prefix(n[:5], 'initials_prefix', w)
    if found: return result('review')
    return result('too_broad' if truncated else 'missing')


if __name__ == '__main__':
    import argparse
    import json
    from contextlib import closing
    from resolver import connect
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('db'); p.add_argument('name'); p.add_argument('--alias',action='append',default=[])
    a=p.parse_args()
    with closing(connect(a.db)) as db:
        print(json.dumps(resolve_smart(db,a.name,a.alias),ensure_ascii=False))
