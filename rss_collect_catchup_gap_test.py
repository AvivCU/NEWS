"""Reproduce collect-only -> full RSS catch-up gap with synthetic gzipped seen log.
Independent model of code reviewed in older Rosario snapshot (not current private main).
"""
import datetime as dt
import pathlib
import tempfile
from rss_seen_gzip_git_race_test import write_gz,read_gz,entry

LOG_NAME="data/seen/"

def put_day(root, day,rows):
    folder=root/("date-"+day)
    # Use the same compressed format as the synthetic Git race test
    write_gz(folder,rows)
    actual=folder/"data/seen/2026-11-23.jsonl.gz"
    dest=root/"data/seen"/(day+".jsonl.gz")
    dest.parent.mkdir(parents=True,exist_ok=True)
    actual.replace(dest)

def load_since(root,day):
    rows=[]
    for p in sorted((root/"data/seen").glob("*.jsonl.gz")):
        if p.name[:10]>=day.isoformat():
            import gzip,json
            with gzip.open(p,"rt",encoding="utf-8") as f:
                rows.extend(json.loads(line) for line in f if line.strip())
    return rows

def cutoff_old(today):
    return today-dt.timedelta(days=2)

def cutoff_since_last_success(today, last_success, keep_days=14):
    """Example only: use recorded successful full-run date, never earlier than retention."""
    floor=today-dt.timedelta(days=keep_days)
    # Include the last successful day itself because it may contain later collect runs
    return max(floor,last_success) if last_success else cutoff_old(today)

def test():
    today=dt.date(2026,11,23)
    with tempfile.TemporaryDirectory(prefix="rss-catchup-") as tmp:
        root=pathlib.Path(tmp)
        put_day(root,"2026-11-19",[entry("collected-nov19","18:00")])
        put_day(root,"2026-11-20",[entry("collected-nov20","21:45")])
        put_day(root,"2026-11-21",[entry("collected-nov21","11:45")])
        put_day(root,"2026-11-22",[entry("collected-nov22","11:45")])
        put_day(root,"2026-11-23",[entry("today","07:00")])
        old={r["l"] for r in load_since(root,cutoff_old(today))}
        assert "https://example.invalid/collected-nov20" not in old
        assert "https://example.invalid/collected-nov21" in old
        print("GAP_OLD_2DAY: Nov20 collected-only article invisible to full scan on Nov23")

        safe=cutoff_since_last_success(today,dt.date(2026,11,19),14)
        recovered={r["l"] for r in load_since(root,safe)}
        assert "https://example.invalid/collected-nov20" in recovered
        assert len(recovered)==5
        print("GAP_WATERMARK: all five saved synthetic items available after skipped full runs")

        # No persisted watermark: fallback identical to current two-day window
        assert cutoff_since_last_success(today,None,14)==cutoff_old(today)
        # Long outages cannot be claimed complete outside retention.
        assert cutoff_since_last_success(today,dt.date(2026,10,1),14)==dt.date(2026,11,9)
        # Multiple full runs in same day should reread saved log and rely on URL dedup.
        assert cutoff_since_last_success(today,today,14)==today
        print("GAP_POLICY_TESTS=5/5")

if __name__=="__main__":test()
