"""Durable full-scan watermark prototype. All data are synthetic.
The commit boundary must be AFTER successful remote state save, not before it.
"""
import datetime as dt
import gzip
import json
import pathlib
import tempfile

UTC=dt.timezone.utc
def utc(s):
    t=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.tzinfo is None: raise ValueError("naive timestamp unsupported")
    return t.astimezone(UTC)
def save(p,thing):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(thing,sort_keys=True)+"\n")
def read(p):
    return json.loads(p.read_text()) if p.exists() else {}
def cutoff(last_success, now, retention_days=30, safety_hours=3):
    """Watermark includes an overlap for collections committing during full scan.
    Does not claim to recover beyond retention or non-indexed feed gaps.
    """
    if retention_days < 1:raise ValueError("invalid retention")
    floor=now-dt.timedelta(days=retention_days)
    if not last_success:return floor
    return max(floor, utc(last_success)-dt.timedelta(hours=safety_hours))
def scan(paths, since, already_processed):
    """Read saved gzip JSONL daily logs through now; no Monday writes."""
    selected=[]
    for p in sorted(paths):
        # Never hide gzip errors or reinterpret a corrupt file as empty.
        with gzip.open(p,"rt",encoding="utf-8") as f:
            for raw in f:
                if not raw.strip():continue
                obj=json.loads(raw)
                if utc(obj["collected_at"])>=since and obj["url"] not in already_processed:
                    selected.append(obj)
    # Stable de-dup; prefer first appearance for processing; actual matching may require update handling
    unique={}
    for obj in sorted(selected,key=lambda x:x["collected_at"]):
        unique.setdefault(obj["url"],obj)
    return list(unique.values())
def gzip_rows(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("wb") as f:
        with gzip.GzipFile(filename="",mode="wb",fileobj=f,mtime=0) as gz:
            gz.write("".join(json.dumps(x)+"\n" for x in rows).encode())
def commit_successful_full_scan(watermark, start_at, *, all_outputs_remote_saved, has_errors):
    if has_errors or not all_outputs_remote_saved:
        return watermark
    previous=watermark.get("last_full_scan_success")
    current=utc(start_at)
    if previous and current<utc(previous):
        raise ValueError("clock moved backwards / concurrent outdated checkpoint")
    return {"last_full_scan_success":current.isoformat()}

def test_outage():
    now=utc("2026-11-23T09:00:00Z")
    with tempfile.TemporaryDirectory() as d:
        root=pathlib.Path(d)
        p=root/"data/seen/2026-11-20.jsonl.gz"
        gzip_rows(p,[{"url":"https://example.invalid/A","collected_at":"2026-11-20T18:00:00Z"}])
        since=cutoff("2026-11-19T08:00:00Z",now)
        assert [x["url"] for x in scan([p],since,set())]==["https://example.invalid/A"]
        assert scan([p],now-dt.timedelta(days=2),set())==[]
        print("OUTAGE: older collected-only article recovered")

def test_idempotence():
    now=utc("2026-11-23T09:00:00Z")
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/"seen.jsonl.gz"
        gzip_rows(p,[{"url":"https://example.invalid/A","collected_at":"2026-11-22T08:00:00Z"},{"url":"https://example.invalid/A","collected_at":"2026-11-22T10:00:00Z"}])
        since=cutoff(None,now)
        once=scan([p],since,set())
        assert len(once)==1
        assert scan([p],since,{x["url"] for x in once})==[]
        print("IDEMPOTENCE: one URL once, rerun yields zero")

def test_failed_save_never_advances():
    old={"last_full_scan_success":"2026-11-19T08:00:00+00:00"}
    start="2026-11-23T08:00:00Z"
    assert commit_successful_full_scan(old,start,all_outputs_remote_saved=False,has_errors=False)==old
    assert commit_successful_full_scan(old,start,all_outputs_remote_saved=True,has_errors=True)==old
    updated=commit_successful_full_scan(old,start,all_outputs_remote_saved=True,has_errors=False)
    assert updated["last_full_scan_success"]=="2026-11-23T08:00:00+00:00"
    print("COMMIT_BOUNDARY: failed write or scan cannot advance checkpoint")

def test_concurrent_checkpoint_order():
    newer={"last_full_scan_success":"2026-11-23T08:00:00+00:00"}
    try:commit_successful_full_scan(newer,"2026-11-23T07:00:00Z",all_outputs_remote_saved=True,has_errors=False)
    except ValueError:pass
    else:raise AssertionError("older run reverted checkpoint")
    print("CONCURRENCY: stale full scan cannot move successful checkpoint backwards")

def test_retention_limitation():
    now=utc("2026-11-23T09:00:00Z")
    assert cutoff("2026-10-01T00:00:00Z",now)==now-dt.timedelta(days=30)
    assert cutoff(None,now)==now-dt.timedelta(days=30)
    print("RETENTION: cannot claim completeness before retained history")

def test_corrupt_gzip_fails_closed():
    now=utc("2026-11-23T09:00:00Z")
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/"seen.jsonl.gz"
        gzip_rows(p,[{"url":"https://example.invalid/A","collected_at":"2026-11-22T08:00:00Z"}])
        contents=p.read_bytes();p.write_bytes(contents[:15])
        try:scan([p],cutoff(None,now),set())
        except (EOFError,OSError):pass
        else:raise AssertionError("bad gzip silently swallowed")
        print("CORRUPT_GZIP: scanner fails rather than silently discarding data")

def test_cross_midnight_overlap():
    now=utc("2026-11-23T09:00:00Z")
    cut=cutoff("2026-11-22T22:30:00Z",now)
    assert cut==utc("2026-11-22T19:30:00Z")
    print("MIDNIGHT: timestamps not local-date cutoff")

if __name__=="__main__":
    for fn in [test_outage,test_idempotence,test_failed_save_never_advances,test_concurrent_checkpoint_order,test_retention_limitation,test_corrupt_gzip_fails_closed,test_cross_midnight_overlap]:
        fn()
    print("DURABLE_WATERMARK_TESTS=7/7")
