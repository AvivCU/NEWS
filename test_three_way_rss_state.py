"""Regression suite for conservative three-way state merge.
Uses disposable synthetic RSS/Monday-shaped records; no secrets, external writes.
"""
import copy
import json
from three_way_rss_state import merge_json_state, StateConflict

A = "https://example.invalid/article-a"
B = "https://example.invalid/article-b"

def conflict(base, local, remote):
    try: merge_json_state(base,local,remote)
    except StateConflict: return
    raise AssertionError("Expected StateConflict: "+str((base,local,remote)))

def test():
    cases = 0
    def ok(cond, label):
        nonlocal cases
        assert cond,label
        cases+=1

    base={"hits":{"card42":[{"l":"https://example.invalid/old","d":"2026-11-22"}]},
          "body_fails":{},
          "bodies":{},
          "sources":{"globes":{"items":10,"run_id":"baseline"}},
          "meta":{"full_ok":"2026-11-22T04:00:00Z"}}
    local=copy.deepcopy(base)
    remote=copy.deepcopy(base)
    local["hits"]["card42"].append({"l":A,"wt":"2026-11-23T08:00:00Z"})
    remote["hits"]["card42"].append({"l":B,"wt":"2026-11-23T08:01:00Z"})
    before=(copy.deepcopy(base),copy.deepcopy(local),copy.deepcopy(remote))
    merged=merge_json_state(base,local,remote)
    ok(len(merged["hits"]["card42"])==3,"two additions same card")
    ok(merged["hits"]["card42"][1]["l"]==B,"remote additions retained")
    ok(merged["hits"]["card42"][2]["wt"]=="2026-11-23T08:00:00Z","local wt retained")
    ok((base,local,remote)==before,"no input mutation")

    local["body_fails"][A]={"retry_attempts":2}
    remote["body_fails"][B]={"retry_attempts":4}
    merged=merge_json_state(base,local,remote)
    ok(set(merged["body_fails"])=={A,B},"retry entries both retained")

    # Isolate independent recovery and stale remote failure with no parallel retry edit.
    local["body_fails"].pop(A)
    local["bodies"][A]="2026-11-23T09:05:00Z"
    remote["body_fails"][A]={"retry_attempts":3}
    conflict(base,local,remote)
    ok(True,"concurrent body recovery and retry fails closed")

    conflict({"body_fails":{A:{"retry_attempts":1}}},
             {"body_fails":{A:{"retry_attempts":2}}},
             {"body_fails":{A:{"retry_attempts":3}}})
    ok(True,"conflicting retry counter fails closed")

    conflict({"hits":{"card42":[{"l":A}]}},
             {"hits":{"card42":[]}},
             {"hits":{"card42":[{"l":A},{"l":B}]}})
    ok(True,"deletion vs append conflict")

    conflict({"hits":{"card42":[{"l":A}]}},
             {"hits":{"card42":[{"l":B}]}},
             {"hits":{"card42":[{"l":A},{"l":B}]}})
    ok(True,"prior list rewrite rejected")

    conflict({"meta":{"full_ok":"2026-11-22T04:00:00Z"}},
             {"meta":{"full_ok":"2026-11-23T04:00:00Z"}},
             {"meta":{"full_ok":"2026-11-23T08:00:00Z"}})
    ok(True,"full_ok simultaneous change flagged")

    conflict({"sources":{"globes":{"items":10,"run_id":"base"}}},
             {"sources":{"globes":{"items":15,"run_id":"A"}}},
             {"sources":{"globes":{"items":20,"run_id":"B"}}})
    ok(True,"sources metrics conflict flagged")

    conflict({"hits":{"card42":[{"l":A}]}},
             {"hits":{"card42":[{"l":A},{"l":B}]}},
             {"hits":{"card42":[]}})
    ok(True,"deletion vs addition conflict")

    same=merge_json_state({"x":{"y":1}},{"x":{"y":2}},{"x":{"y":2}})
    ok(same=={"x":{"y":2}},"same edit succeeds")

    remote_new=merge_json_state({},{"hits":{"a":[{"l":A}]}},{"hits":{"b":[{"l":B}]}})
    ok(set(remote_new["hits"])=={"a","b"},"two distinct nested dict creations")

    # Same new list built by both runners should not duplicate.
    same_added=merge_json_state({},{"hits":{"a":[{"l":A}]}},{"hits":{"a":[{"l":A}]}})
    ok(same_added["hits"]["a"]==[{"l":A}],"identical additions deduplicated")

    conflict({"hits":{"a":[{"l":A}]}},{"hits":{}},{"hits":{"a":[{"l":A},{"l":B}]}})
    ok(True,"deletion of dictionary key vs edit fails")

    # A text-like article remains a scalar and is not silently replaced.
    conflict({"bodies":{A:"body 1"}},{"bodies":{A:"body 2"}},{"bodies":{A:"body 3"}})
    ok(True,"conflicting body rewrite fails")

    print(f"THREE_WAY_MERGE_ASSERTIONS={cases}/{cases}")
    print("THREE_WAY_SCOPE=prototype; production state helper not inspected")

if __name__=="__main__":test()
