"""Reproduce concurrent GitHub state writes with real local git remotes.
No private data, network sources, Monday, or state persistence.
"""
import json
import os
import pathlib
import subprocess
import tempfile

def run(*args, cwd=None, check=True):
    p=subprocess.run(args,cwd=cwd,capture_output=True,text=True)
    if check and p.returncode:raise RuntimeError(f"{args}: {p.stderr[-1000:]}")
    return p

def init_repo(root):
    bare=root/"remote.git"
    run("git","init","--bare","--initial-branch=main",str(bare))
    seed=root/"seed";run("git","clone",str(bare),str(seed))
    git_setup(seed)
    write_state(seed,{"articles":{}})
    run("git","add","rss_state.json",cwd=seed)
    run("git","commit","-m","seed",cwd=seed)
    run("git","push","origin","HEAD:main",cwd=seed)
    clients={}
    for n in ("A","B"):
        p=root/n;run("git","clone",str(bare),str(p));git_setup(p);clients[n]=p
    return bare,clients

def git_setup(p):
    run("git","config","user.email","news-race-test@example.invalid",cwd=p)
    run("git","config","user.name","Synthetic Test",cwd=p)

def read_state(p):
    return json.loads((p/"rss_state.json").read_text())

def write_state(p,s):
    (p/"rss_state.json").write_text(json.dumps(s,sort_keys=True,ensure_ascii=False,indent=2)+"\n")

def commit(p,msg):
    run("git","add","rss_state.json",cwd=p)
    run("git","commit","-m",msg,cwd=p)

def safe_merge(current,remote):
    merged={"articles":dict(remote["articles"])}
    for article,local_values in current["articles"].items():
        if article not in merged["articles"]:
            merged["articles"][article]=local_values
            continue
        v=dict(merged["articles"][article])
        for field,value in local_values.items():
            if field not in v:
                v[field]=value
            elif field=="retry_attempts":
                v[field]=max(int(v[field]),int(value))
            elif field=="first_seen":
                v[field]=min(v[field],value)
            elif field=="last_seen":
                v[field]=max(v[field],value)
            elif v[field]!=value:
                raise ValueError(f"CONFLICT_REQUIRES_REVIEW: {article}.{field}: {v[field]} vs {value}")
        merged["articles"][article]=v
    return merged

def test_unsafe(root):
    bare,c=init_repo(root)
    a,b=c["A"],c["B"]
    write_state(a,{"articles":{"article-a":{"retry_attempts":2,"first_seen":"2026-11-23T07:00:00Z"}}})
    commit(a,"A retry updated")
    write_state(b,{"articles":{"article-b":{"wt":"2026-11-23T08:00:00Z","last_seen":"2026-11-23T08:00:00Z"}}})
    commit(b,"B arrival updated")
    run("git","push","origin","HEAD:main",cwd=a)
    rebased=run("git","pull","--rebase","--autostash","-X","theirs","origin","main",cwd=b,check=False)
    if rebased.returncode==0:
        pushed=run("git","push","origin","HEAD:main",cwd=b,check=False)
        assert pushed.returncode==0,pushed.stderr
        final=json.loads(run("git","--git-dir",str(bare),"show","main:rss_state.json").stdout)
        retained=set(final["articles"])
        assert retained!={"article-a","article-b"},f"Unexpectedly preserved both under unsafe policy: {final}"
        assert retained in ({"article-a"},{"article-b"}),retained
        print("UNSAFE_REBASE: success_code=0; silently_lost="+str(({"article-a","article-b"}-retained).pop())+"; retained="+str(sorted(retained)))
    else:
        print("UNSAFE_REBASE: conflict/failed pull; code="+str(rebased.returncode))

def test_safe(root):
    bare,c=init_repo(root)
    a,b=c["A"],c["B"]
    write_state(a,{"articles":{"article-a":{"retry_attempts":2,"first_seen":"2026-11-23T07:00:00Z"}}})
    commit(a,"A retry updated")
    write_state(b,{"articles":{"article-b":{"wt":"2026-11-23T08:00:00Z","last_seen":"2026-11-23T08:00:00Z"}}})
    commit(b,"B arrival updated")
    run("git","push","origin","HEAD:main",cwd=a)
    pending=read_state(b)
    run("git","fetch","origin","main",cwd=b)
    upstream=json.loads(run("git","show","origin/main:rss_state.json",cwd=b).stdout)
    combined=safe_merge(pending,upstream)
    run("git","reset","--hard","origin/main",cwd=b)
    write_state(b,combined);commit(b,"B merged from live remote")
    run("git","push","origin","HEAD:main",cwd=b)
    final=json.loads(run("git","--git-dir",str(bare),"show","main:rss_state.json").stdout)
    assert set(final["articles"])=={"article-a","article-b"},final
    assert final["articles"]["article-a"]["retry_attempts"]==2
    assert final["articles"]["article-b"]["wt"]=="2026-11-23T08:00:00Z"
    print("SAFE_SEMANTIC_MERGE: both records, retries and wt retained")

def test_same_article_fields():
    original={"articles":{"article-a":{"retry_attempts":1,"first_seen":"2026-11-22T12:00:00Z"}}}
    local={"articles":{"article-a":{"retry_attempts":2,"last_seen":"2026-11-23T08:00:00Z"}}}
    result=safe_merge(local,original)
    assert result["articles"]["article-a"]=={"retry_attempts":2,"first_seen":"2026-11-22T12:00:00Z","last_seen":"2026-11-23T08:00:00Z"}
    changed={"articles":{"article-a":{"status":"matched"}}}
    remote={"articles":{"article-a":{"status":"failed"}}}
    try:safe_merge(changed,remote)
    except ValueError as e:
        assert "CONFLICT_REQUIRES_REVIEW" in str(e)
    else:raise AssertionError("Dangerous status conflict accepted")
    print("SAME_ARTICLE_FIELDS: retries merged; status conflict detected (fail closed)")

if __name__=="__main__":
    with tempfile.TemporaryDirectory(prefix="rss-git-race-") as d:
        root=pathlib.Path(d)
        (root/"unsafe").mkdir();test_unsafe(root/"unsafe")
        (root/"safe").mkdir();test_safe(root/"safe")
    test_same_article_fields()
    print("PASS: 3 scenarios on real Git; no external writes")
