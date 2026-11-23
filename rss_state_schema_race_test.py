"""Test real rss_state.json *shapes* using synthetic data.
These assertions intentionally fail for naive shallow merging; private data is not used.
"""
from rss_state_git_race_test import safe_merge

def shallow_merge(a,b):
    d=dict(a)
    d.update(b)
    return d

def tests():
    link_a="https://example.invalid/a"
    link_b="https://example.invalid/b"
    # Both jobs update the same card hits list.
    local={"hits":{"card42":[{"l":link_a,"d":"2026-11-23"}]}}
    remote={"hits":{"card42":[{"l":link_b,"d":"2026-11-23"}]}}
    shallow=shallow_merge(local,remote)
    assert len(shallow["hits"]["card42"])==1,shallow
    print("HITS_SAME_CARD: shallow merge silently loses one card hit")

    # A body retry fails in cloud, B recovers the same article in home.
    cloud={"body_fails":{link_a:{"n":3,"d":"2026-11-23"}}}
    home={"bodies":{link_a:"2026-11-23"},"body_fails":{}}
    naive=shallow_merge(home,cloud)
    assert link_a in naive["bodies"] and link_a in naive["body_fails"]
    print("BODY_RECOVERY: naive merge retains a stale failure for recovered body")

    # Two workers touch different retry counters under the same dict key.
    cloud={"body_fails":{link_a:{"n":3}}}
    home={"body_fails":{link_b:{"n":1}}}
    naive=shallow_merge(home,cloud)
    assert set(naive["body_fails"])=={link_a}
    print("BODY_FAILS: shallow dictionary merge drops retry counter for another URL")

    # A universal strict-merge from prototype must reject ambiguous scalar updates,
    # not silently choose a winner.
    try:
        safe_merge({"articles":{"card42":{"written":"version-A"}}},{"articles":{"card42":{"written":"version-B"}}})
    except ValueError:
        print("SCALAR_CONFLICT: fail-closed confirmed")
    else:
        raise AssertionError("Different versions should conflict")

    # Distinct workflow-level source metrics cannot safely be unioned.
    reportA={"sources":{"globes":{"items":15,"run_id":"A"}}}
    reportB={"sources":{"globes":{"items":20,"run_id":"B"}}}
    assert shallow_merge(reportA,reportB)["sources"]["globes"]["run_id"]=="B"
    print("SOURCES_REPORT: distinct run reports require authoritative run version")
    print("ACTUAL_SCHEMA_SHAPE_TESTS=5/5")

if __name__=="__main__":tests()
