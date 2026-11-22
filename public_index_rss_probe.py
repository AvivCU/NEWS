"""Smoke test Bing's documented RSS search output as a *secondary* discovery
channel. An index is NOT proof of exhaustive original source coverage.
"""
import json,urllib.request,urllib.parse,xml.etree.ElementTree as ET,datetime
from pathlib import Path
QUERIES={
 "nta_single_supplier":'site:nta.co.il/tenders3/ "2026"',
 "nta_tenders":'site:nta.co.il/tenders/ "2026"',
 "gov_emission_documents":'site:gov.il/BlobFolder/dynamiccollectorresultitem/ "air_emission_permits_2026"',
 "rail_tender_pdf":'site:tender.rail.co.il/tmedia/AllTenders/ "2026"',
}
out={"checked_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"results":{}}
for kind,q in QUERIES.items():
 url="https://www.bing.com/search?"+urllib.parse.urlencode({"q":q,"format":"rss"})
 info={"q":q}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={"Accept":"application/rss+xml,application/xml","User-Agent":"RosarioPublicFeedPublicRSSAudit/1.0"}),timeout=22) as res:
   raw=res.read(500000)
   info["http"]=res.status;info["bytes"]=len(raw);info["type"]=res.headers.get("Content-Type")
  xml=ET.fromstring(raw);items=xml.findall("./channel/item")
  info["count"]=len(items)
  info["examples"]=[{"title":x.findtext("title"),"link":x.findtext("link"),"pubDate":x.findtext("pubDate")} for x in items[:7]]
 except Exception as e:info["error"]=str(e)[:250]
 out["results"][kind]=info
 print(kind,json.dumps(info,ensure_ascii=False)[:2200],flush=True)
Path("official_index_rss_audit.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf8")
