"""Independent, read-only probe: RSS publication after a date-only scan marker.
No private watchlist/Monday data or source-code copied. Standard library only.
"""
import datetime as dt
import email.utils
import json
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Jerusalem")
CUT = dt.datetime(2026, 11, 23, 7, 12, tzinfo=TZ)
FEEDS = {
    "globes": "https://www.globes.co.il/webservice/rss/rssfeeder.asmx/FeederNode?iID=2",
    "calcalist": "https://www.calcalist.co.il/GeneralRSS/0,16335,L-8,00.xml",
    "ynet": "https://www.ynet.co.il/Integration/StoryRss6.xml",
    "ice": "https://www.ice.co.il/rss.xml",
}

def parse_date(s):
    if not s: return None
    try:
        t = email.utils.parsedate_to_datetime(s)
        return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).astimezone(TZ)
    except (ValueError, TypeError, IndexError):
        pass
    try:
        t = dt.datetime.fromisoformat(s.replace("Z","+00:00"))
        return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).astimezone(TZ)
    except (ValueError, TypeError):
        return None

def old_excludes(pub):
    return pub.date() <= CUT.date()

def self_test():
    assert old_excludes(CUT - dt.timedelta(minutes=1))
    assert old_excludes(CUT + dt.timedelta(minutes=1))
    assert CUT + dt.timedelta(minutes=1) > CUT
    assert not old_excludes(CUT + dt.timedelta(days=1))
    assert parse_date("Mon, 23 Nov 2026 08:00:00 +0200").hour == 8
    assert parse_date("2026-11-23T06:00:00Z").hour == 8
    assert parse_date("bad") is None
    print("OFFLINE_CASES=7/7")

def probe():
    sources, candidates = [], []
    for name, url in FEEDS.items():
        result = {"source":name}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"RosarioReadOnlyResearch/1.0"}),timeout=20) as response:
                data = response.read(2_000_000)
                result["http"] = response.status
            root = ET.fromstring(data)
            items = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
            result["items"], result["dated"] = len(items), 0
            for item in items:
                pub = None
                for tag in ["pubDate", "{http://purl.org/dc/elements/1.1/}date", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"]:
                    pub = parse_date(item.findtext(tag))
                    if pub: break
                if not pub: continue
                result["dated"] += 1
                if pub.date() == CUT.date() and pub > CUT:
                    title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or ""
                    candidates.append({"source":name,"published":pub.isoformat(),"title":title[:100],"excluded_by_date_only":old_excludes(pub)})
            result["same_day_after_scan"] = sum(x["source"]==name for x in candidates)
        except Exception as e:
            result["error"] = type(e).__name__ + ": " + str(e)[:140]
        sources.append(result)
    report = {"cutoff_israel":CUT.isoformat(),"sources":sources,"same_day_candidates":len(candidates),"examples":candidates[:15],"scope":"Public RSS only; no watchlist. Does NOT establish actual lost watched-company articles."}
    print("LIVE_RESULT="+json.dumps(report,ensure_ascii=False))
    assert any("http" in r for r in sources), "No live RSS source reachable"

if __name__=="__main__":
    self_test()
    probe()
