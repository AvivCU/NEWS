"""Synthetic benchmark: full rematch vs targeted company identity rematch.
Research only: NOT Rosario's production matcher. Tests exact output equality,
including a removed company alias, added alias, and new articles.
"""
import json
import random
import statistics
import time

N_ARTICLES=17296
N_COMPANIES=889
CHANGED_IDS=(11,120,221,700)
NEW_ARTICLES=600

def identity(cid):
    return "firm%04d" % cid

def build_fixture():
    random.seed(42)
    articles=[]
    for i in range(N_ARTICLES+NEW_ARTICLES):
        company=(i*67+11)%N_COMPANIES
        token=identity(company)
        # Some stories mention a secondary company.
        second=(company+101)%N_COMPANIES if i%29==0 else None
        tokens={token}
        if second is not None:tokens.add(identity(second))
        if i%131==0 and company in CHANGED_IDS:tokens.add("legacy%04d"%company)
        articles.append(frozenset(tokens))
    return articles

def initial_profiles():
    return {i:{identity(i)} for i in range(N_COMPANIES)}

def modified_profiles():
    p=initial_profiles()
    for i in CHANGED_IDS:
        p[i].add("legacy%04d"%i)
    # Alias removal as well (must remove an old cached match).
    p[11].remove(identity(11))
    return p

def article_matches(tokens,aliases):
    return not tokens.isdisjoint(aliases)

def full_match(articles,profiles):
    return {company:{i for i,tokens in enumerate(articles) if article_matches(tokens,aliases)}
            for company,aliases in profiles.items()}

def partial_match(articles,profiles,previous,old_count,changed):
    result={company:set(items) for company,items in previous.items()}
    # Reevaluate *all history* for companies whose identity changed.
    for company in changed:
        result[company]={i for i,tokens in enumerate(articles) if article_matches(tokens,profiles[company])}
    # Only brand-new articles need matching against unchanged companies.
    for company,aliases in profiles.items():
        if company in changed:continue
        result[company].update(
            i for i in range(old_count,len(articles)) if article_matches(articles[i],aliases)
        )
    return result

def test():
    articles=build_fixture()
    old_articles=articles[:N_ARTICLES]
    original=initial_profiles()
    changed=modified_profiles()
    t0=time.perf_counter();baseline=full_match(old_articles,original);initial_sec=time.perf_counter()-t0
    t0=time.perf_counter();expected=full_match(articles,changed);full_sec=time.perf_counter()-t0
    t0=time.perf_counter();actual=partial_match(articles,changed,baseline,N_ARTICLES,set(CHANGED_IDS));partial_sec=time.perf_counter()-t0
    assert actual==expected,"Targeted rematch diverges from full output"
    assert sum(map(len,actual.values()))==sum(map(len,expected.values()))
    assert actual[11]!=baseline[11]  # Removed alias must be reflected.
    # Old stories can match a new alias: must recheck changed identities against history.
    assert any(i<N_ARTICLES for i in actual[11]^baseline[11])
    # Running the same cycle again must be idempotent.
    same=partial_match(articles,changed,actual,len(articles),set())
    assert same==expected
    # A changed-company profile can have no hits and needs to erase the old set.
    no_alias={k:set(v) for k,v in changed.items()}
    no_alias[11]=set()
    no_company=partial_match(articles,no_alias,actual,len(articles),{11})
    assert no_company[11]==set()
    assert all(no_company[k]==expected[k] for k in expected if k!=11)
    full_checks=len(articles)*N_COMPANIES
    partial_checks=len(articles)*len(CHANGED_IDS) + NEW_ARTICLES*(N_COMPANIES-len(CHANGED_IDS))
    report={"note":"Synthetic matcher benchmark; NOT production runtime estimate",
            "articles_total":len(articles),"historical":N_ARTICLES,
            "new_articles":NEW_ARTICLES,"companies":N_COMPANIES,
            "changed_companies":len(CHANGED_IDS),
            "full_identity_checks":full_checks,
            "targeted_identity_checks":partial_checks,
            "check_reduction_pct":round(100*(1-partial_checks/full_checks),2),
            "full_runtime_s":round(full_sec,4),
            "targeted_runtime_s":round(partial_sec,4),
            "initial_runtime_s":round(initial_sec,4),
            "equal_outputs":True,"idempotent":True,
            "handles_alias_remove":True,"handles_old_article_new_alias":True}
    print("REMATCH_BENCHMARK="+json.dumps(report,ensure_ascii=False))
    print("REMATCH_TESTS=5/5")

if __name__=="__main__":test()
