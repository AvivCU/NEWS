"""Standalone Task 7 same-day cutoff prototype; no private data or Monday writes."""
import datetime as dt
import re
import urllib.parse
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Asia/Jerusalem")
SCAN_RE=re.compile(r"^סריקה\s+(\d{2})\.(\d{2})\.(\d{2})(?:\s+(\d{2}):(\d{2}))?\s*:",re.M)

def latest_scan(notes):
    scans=[]
    for day,month,year,hour,minute in SCAN_RE.findall(notes or ""):
        try:
            d=dt.date(2000+int(year),int(month),int(day))
            t=dt.datetime.combine(d,dt.time(int(hour),int(minute)),TZ) if hour else None
            scans.append((d,t))
        except ValueError: pass
    return max(scans,key=lambda x:(x[0],x[1] or dt.datetime.min.replace(tzinfo=TZ))) if scans else None

def parse_timestamp(s):
    if not s:return None
    try:
        t=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
        return (t if t.tzinfo else t.replace(tzinfo=TZ)).astimezone(TZ)
    except ValueError:return None

def canonical_url(url):
    p=urllib.parse.urlsplit(url.strip())
    q=urllib.parse.parse_qsl(p.query,keep_blank_values=True)
    q=[(k,v) for k,v in q if not k.lower().startswith("utm_") and k.lower() not in ("fbclid","gclid")]
    host=(p.hostname or "").lower().removeprefix("www.")
    return urllib.parse.urlunsplit((p.scheme.lower() or "https",host+(":"+str(p.port) if p.port else ""),p.path.rstrip("/") or "/",urllib.parse.urlencode(sorted(q)),""))

def classify(article,scan,handled_urls=()):
    if canonical_url(article["url"]) in {canonical_url(x) for x in handled_urls}:return "handled"
    if not scan:return "candidate_no_scan"
    day,exact=scan
    published=parse_timestamp(article.get("published_at"))
    if published:
        if exact:return "candidate_after_scan" if published>exact else "before_scan"
        if published.date()>day:return "candidate_after_scan"
        if published.date()<day:return "before_scan"
        return "candidate_same_day_legacy_uncertain"
    try:d=dt.date.fromisoformat(article.get("published_date",""))
    except (ValueError,TypeError):return "unknown_date_review"
    if d>day:return "candidate_after_scan"
    if d<day:return "before_scan"
    return "candidate_same_day_no_publication_time"

def test():
    scan=latest_scan("סריקה 23.11.26 07:12: טופל https://example.org/old")
    assert scan[1].hour==7 and scan[1].minute==12
    assert classify({"url":"https://x.co/a","published_at":"2026-11-23T08:23:00+02:00"},scan)=="candidate_after_scan"
    assert classify({"url":"https://x.co/b","published_at":"2026-11-23T07:11:00+02:00"},scan)=="before_scan"
    old=latest_scan("סריקה 23.11.26: בדיקה")
    assert old[1] is None
    assert classify({"url":"https://x.co/a","published_at":"2026-11-23T08:23:00+02:00"},old)=="candidate_same_day_legacy_uncertain"
    assert classify({"url":"https://x.co/a","published_date":"2026-11-23"},scan)=="candidate_same_day_no_publication_time"
    assert classify({"url":"https://x.co/a","published_at":"2026-11-22T23:59:00+02:00"},old)=="before_scan"
    assert classify({"url":"https://x.co/a?utm_source=foo","published_at":"2026-11-24T08:23:00+02:00"},scan,["https://www.x.co/a"])=="handled"
    assert classify({"url":"https://x.co/a","published_at":"2026-11-24T08:23:00+02:00"},None)=="candidate_no_scan"
    assert classify({"url":"https://x.co/a","published_date":"bad"},scan)=="unknown_date_review"
    assert latest_scan("סריקה 31.02.26: broken") is None
    assert latest_scan("סריקה 22.11.26: old\nסריקה 23.11.26 07:12: new")==scan
    assert classify({"url":"https://x.co/a","published_at":"2026-11-23T06:23:00Z"},scan)=="candidate_after_scan"
    print("CUTOFF_POLICY_TESTS=12/12")

if __name__=="__main__":test()
