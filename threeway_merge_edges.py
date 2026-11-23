"""PR #68 risk assessment on SYNTHETIC state, independent of inaccessible private patch.
3-way merge: compare base vs local vs remote; concurrency must not silently lose writes.
No private data, Monday calls, or Rosario code. This is a regression specification.
"""
from copy import deepcopy

MISSING = object()
def threeway(base, ours, theirs, *, conflict="raise"):
    """Demonstration ONLY: top-level 3-way semantics, not a full Rosario merger."""
    merged={}
    for key in base.keys() | ours.keys() | theirs.keys():
        b=base.get(key,MISSING); o=ours.get(key,MISSING); t=theirs.get(key,MISSING)
        local_changed = o!=b
        remote_changed = t!=b
        if local_changed and remote_changed and o!=t:
            if conflict=="raise":
                raise ValueError(f"conflict:{key}")
            chosen= o if conflict=="ours" else t
        elif local_changed:
            chosen=o
        else:
            chosen=t
        if chosen is not MISSING:
            merged[key]=deepcopy(chosen)
    return merged

def last_writer_wins(base,ours,theirs,local_run_start,remote_run_start):
    # Simplified policy; intentionally models danger of ordering by run timestamp.
    return threeway(base,ours,theirs,conflict=("ours" if local_run_start>=remote_run_start else "theirs"))

def check(fn):
    try:fn()
    except Exception as e:
        print("FAIL",fn.__name__,repr(e))
        raise
    print("PASS",fn.__name__)

def deletion_vs_unchanged():
    b={"A":{"url":"a"}}
    assert threeway(b,{},b)=={}
    assert threeway(b,b,{})=={}

def deletion_vs_concurrent_edit():
    b={"A":{"wt":"07:00"}}
    edited={"A":{"wt":"08:00"}}
    try:threeway(b,{},edited)
    except ValueError:pass
    else:raise AssertionError("Deletion vs edit must not be silently resolved")

def accidental_reintroduction_from_stale_base():
    b={"A":{"url":"a"}}
    # Remote intentionally deletes A; our runner has not touched it.
    assert threeway(b,b,{})=={}

def concurrent_appends_same_parent():
    # Need merge by URL inside 'hits[company]', not 3-way replacement of entire list.
    b={"company":[]}
    ours={"company":[{"url":"a"}]}
    theirs={"company":[{"url":"b"}]}
    try:threeway(b,ours,theirs)
    except ValueError:pass
    else:raise AssertionError("Two list appends should be flagged for element-level merge")
    expected={"a","b"}
    assert set(x["url"] for x in ours["company"]+theirs["company"])==expected

def newer_run_is_not_newer_information():
    b={"article":{"state":"pending","updated_at":"2026-11-23T07:00Z"}}
    # A started earlier, fetched data at 10:00; B started later but fetched at 09:00.
    ours={"article":{"state":"recovered","updated_at":"2026-11-23T10:00Z"}}
    theirs={"article":{"state":"failed","updated_at":"2026-11-23T09:00Z"}}
    selected=last_writer_wins(b,ours,theirs,100,101)
    assert selected["article"]["state"]=="failed"
    assert ours["article"]["updated_at"]>theirs["article"]["updated_at"]
    print("EVIDENCE: newer run start can select stale semantic information")

def retry_count_reset():
    b={"failure":{"n":4}}
    ours={"failure":{"n":5}}
    theirs={}
    # Recovery removes 'failure'; simple max count has no sensible definition when deleted.
    try:threeway(b,ours,theirs)
    except ValueError:pass
    else:raise AssertionError("Recovery deletion vs retry increment must be explicit")

def duplicate_hit_url_modified():
    base={"hits":[{"url":"a","wt":"2026-11-23T08:00:00Z","title":"First"}]}
    l={"hits":[{"url":"a","wt":"2026-11-23T07:50:00Z","title":"First"}]}
    r={"hits":[{"url":"a","wt":"2026-11-23T08:00:00Z","title":"Changed title"}]}
    try:threeway(base,l,r)
    except ValueError:pass
    else:raise AssertionError("Stable URL with different subfield edits requires field-level merge")

def pruning_14day_boundary():
    base={"old":{"last_seen":"2026-11-08T00:00Z"}}
    ours={}
    theirs={"old":{"last_seen":"2026-11-23T08:00Z"}}
    try:threeway(base,ours,theirs)
    except ValueError:pass
    else:raise AssertionError("Prune vs observed again must use data age at commit and source validity")

def no_conflict_passthrough():
    b={"A":{"url":"a"}}
    o={"A":{"url":"a"},"B":{"url":"b"}}
    t={"A":{"url":"a"},"C":{"url":"c"}}
    assert set(threeway(b,o,t))=={"A","B","C"}

def delete_while_insert_other():
    b={"A":{"url":"a"}}
    o={"B":{"url":"b"}}
    t={"A":{"url":"a"},"C":{"url":"c"}}
    assert set(threeway(b,o,t))=={"B","C"}

if __name__=="__main__":
    for fn in [deletion_vs_unchanged,deletion_vs_concurrent_edit,accidental_reintroduction_from_stale_base,concurrent_appends_same_parent,newer_run_is_not_newer_information,retry_count_reset,duplicate_hit_url_modified,pruning_14day_boundary,no_conflict_passthrough,delete_while_insert_other]:
        check(fn)
    print("EDGE_TESTS=10/10; demo/specification, NOT verification of PR68 code")
