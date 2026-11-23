"""Independent real-git regression: two writers to same gzip JSONL daily log.
No private articles/companies; tests use synthetic URLs and a disposable bare repository.
"""
import gzip
import json
import pathlib
import tempfile
from rss_state_git_race_test import run, git_setup

F="data/seen/2026-11-23.jsonl.gz"

def write_gz(folder, rows):
    p=folder/F
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("wb") as f:
        with gzip.GzipFile(fileobj=f,mode="wb",mtime=0) as gz:
            gz.write(("".join(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n" for row in rows)).encode())

def read_gz(folder):
    with gzip.open(folder/F,"rt",encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def fake_remote(root):
    bare=root/"repo.git";run("git","init","--bare","--initial-branch=main",str(bare))
    seed=root/"seed";run("git","clone",str(bare),str(seed));git_setup(seed)
    write_gz(seed,[]);run("git","add",F,cwd=seed);run("git","commit","-m","seed",cwd=seed);run("git","push","origin","main",cwd=seed)
    clients=[]
    for i in ("cloud","collect"):
        p=root/i;run("git","clone",str(bare),str(p));git_setup(p);clients.append(p)
    return bare,clients

def entry(key, at, read=0):
    return {"l":f"https://example.invalid/{key}","t":f"Title {key}","s":"synthetic",
            "d":"2026-11-23","at":at,"b":read}

def old_style_race(root):
    bare,(a,b)=fake_remote(root)
    write_gz(a,[entry("article-cloud","07:20",1)])
    write_gz(b,[entry("article-collect","07:40",0)])
    for p in (a,b):
        run("git","add",F,cwd=p);run("git","commit","-m","update daily gzip",cwd=p)
    run("git","push","origin","main",cwd=a)
    p=run("git","pull","--rebase","--autostash","-X","theirs","origin","main",cwd=b,check=False)
    if p.returncode==0:
        run("git","push","origin","main",cwd=b)
        final=root/"check";run("git","clone",str(bare),str(final))
        observed={x["l"] for x in read_gz(final)}
        assert len(observed)==1,observed
        print("GZIP_UNSAFE: both snapshots valid gzip; Git push success; one article absent")
    else:
        print("GZIP_UNSAFE: Git detected binary conflict (still blocks save); exit="+str(p.returncode))

def merge_daily(remote,local):
    """Example-only policy: URL is the key; earliest first seen, body flag OR.
    Changing article metadata requires a source-specific decision, not generic JSON merge.
    """
    combined={}
    for row in remote+local:
        key=row["l"]
        if not key:raise ValueError("Missing URL")
        if key not in combined:
            combined[key]=dict(row)
            continue
        prev=combined[key]
        prev["at"]=min(prev["at"],row["at"])
        prev["b"]=max(int(prev.get("b",0)),int(row.get("b",0)))
        # Do not silently overwrite descriptive fields
        for field in ("d","s","t"):
            if prev.get(field)!=row.get(field):
                raise ValueError(f"Conflicting {field} for {key}")
    return sorted(combined.values(),key=lambda x:x["l"])

def safe_race(root):
    bare,(a,b)=fake_remote(root)
    write_gz(a,[entry("article-cloud","07:20",1)])
    write_gz(b,[entry("article-collect","07:40",0),entry("article-cloud","07:10",0)])
    for p in (a,b):
        run("git","add",F,cwd=p);run("git","commit","-m","update daily gzip",cwd=p)
    run("git","push","origin","main",cwd=a)
    pending=read_gz(b)
    run("git","fetch","origin","main",cwd=b)
    run("git","reset","--hard","origin/main",cwd=b)
    updated=merge_daily(read_gz(b),pending)
    write_gz(b,updated)
    run("git","add",F,cwd=b);run("git","commit","-m","merge daily gzip semantic",cwd=b);run("git","push","origin","main",cwd=b)
    final=root/"check";run("git","clone",str(bare),str(final))
    rows=read_gz(final)
    assert len(rows)==2,rows
    row=next(x for x in rows if x["l"].endswith("article-cloud"))
    assert row["at"]=="07:10" and row["b"]==1,row
    print("GZIP_SAFE: two articles preserved, earliest at and successful body flag retained")

def test_corrupt_file():
    with tempfile.TemporaryDirectory(prefix="gzip-corrupt-") as d:
        p=pathlib.Path(d)
        write_gz(p,[entry("real","07:20")])
        path=p/F
        raw=path.read_bytes();path.write_bytes(raw[:max(8,len(raw)//4)])
        try:read_gz(p)
        except (EOFError,OSError):pass
        else:raise AssertionError("Truncated gzip not detected")
        print("GZIP_CORRUPTION: strict reader detects truncation rather than silently resetting daily log")

if __name__=="__main__":
    with tempfile.TemporaryDirectory(prefix="gzip-git-") as d:
        root=pathlib.Path(d);(root/"old").mkdir();(root/"safe").mkdir()
        old_style_race(root/"old");safe_race(root/"safe")
    test_corrupt_file()
    print("GZIP_TESTS=3/3")
