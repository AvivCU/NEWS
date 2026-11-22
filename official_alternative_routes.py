"""Audit official alternate publication paths. Public read-only HTTP requests only."""
import json,re,html,urllib.parse,urllib.request,urllib.error,ssl,datetime
from pathlib import Path
from xml.etree import ElementTree
SITES={
"rail_new_portal":"https://tender.rail.co.il/?page=generalauctions",
"rail_new_robots":"https://tender.rail.co.il/robots.txt",
"rail_new_sitemap":"https://tender.rail.co.il/sitemap.xml",
"rail_modern_main":"https://rail.co.il/?page=generalauctions",
"rail_legacy":"https://www.rail.co.il/tenders/pages/open.aspx",
"rail_public_pdf":"https://tender.rail.co.il/tmedia/AllTenders/b25ba039-1592-43ec-0b96-08decb72c0f0/%D7%9E%D7%95%D7%93%D7%A2%D7%94%20%D7%9C%D7%A2%D7%99%D7%AA%D7%95%D7%9F.pdf",
"nta_no_www":"https://nta.co.il/tenders3/",
"nta_www":"https://www.nta.co.il/tenders3/",
"nta_sitemap":"https://www.nta.co.il/sitemap.xml",
"nta_robots":"https://www.nta.co.il/robots.txt",
"nta_sitemap_no_www":"https://nta.co.il/sitemap.xml",
"gov_publications_rss":"https://www.gov.il/he/api/PublicationApi/rss/c0d8ba69-e309-4fe5-801f-855971774a90",
"gov_news_rss":"https://www.gov.il/he/api/NewsApi/rss/0caee7eb-1ebb-4c12-9ed8-7dce94badcb2",
"gov_dynamic_api":"https://www.gov.il/he/api/DynamicCollector",
"gov_pdf":"https://www.gov.il/BlobFolder/guide/geogeographic_packaging/he/Geogeographic_packaging.pdf",
"ckan_xplan":"https://data.gov.il/api/3/action/package_search?q=xplan&rows=15",
"ckan_plan_online":"https://data.gov.il/api/3/action/package_search?q="+urllib.parse.quote("תוכניות מקוונות")+"&rows=15",
"ckan_emission":"https://data.gov.il/api/3/action/package_search?q="+urllib.parse.quote("היתרי פליטה")+"&rows=15",
"ckan_procurement":"https://data.gov.il/api/3/action/package_search?q="+urllib.parse.quote("התקשרויות")+"&rows=15",
"ags_rest":"https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer?f=json",
"ags_rest_http":"http://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer?f=json",
}
def fetch(name,url):
 info={"url":url}
 req=urllib.request.Request(url,headers={"User-Agent":"Rosario public source study (read only)","Accept":"text/html,application/json,application/rss+xml,application/xml,application/pdf,*/*"})
 try:
  with urllib.request.urlopen(req,timeout=20) as res:
   data=res.read(700000)
   info.update(status=res.status,final_url=res.geturl(),bytes=len(data),content_type=res.headers.get("Content-Type",""))
  if name.startswith("ckan_"):
   o=json.loads(data)
   packages=o.get("result",{}).get("results",[]) if isinstance(o,dict) else []
   info["count"]=o.get("result",{}).get("count")
   info["packages"]=[{"id":p.get("id"),"name":p.get("name"),"title":p.get("title"),"modified":p.get("metadata_modified"),
       "resources":[{"id":v.get("id"),"name":v.get("name"),"format":v.get("format"),"url":v.get("url","")[:180],"created":v.get("created"),"last_modified":v.get("last_modified")} for v in p.get("resources",[])[:6]]} for p in packages[:12]]
  elif "rss" in name:
   o=ElementTree.fromstring(data)
   items=o.findall(".//item")
   info["entries"]=len(items)
   info["samples"]=[{"title":x.findtext("title"),"pubDate":x.findtext("pubDate"),"link":x.findtext("link")} for x in items[:4]]
  elif "pdf" in name:
   info["pdf_magic"]=data.startswith(b"%PDF")
  else:
   s=data.decode("utf8","replace");lo=s.lower()
   info["title"]=(re.search("<title[^>]*>(.*?)</title",s,re.I|re.S).group(1)[:160] if re.search("<title[^>]*>(.*?)</title",s,re.I|re.S) else None)
   info["length_2026"]=s.count("2026")
   info["content_markers"]={t:s.count(t) for t in ["מכרז","ספק יחיד","זוכה","התקשרות","auctionId","api/","MapServer"] if t in s}
   info["scripts"]=[html.unescape(x) for x in re.findall(r'<script[^>]+src=["\x27]([^"\x27]+)',s,re.I)[:10]]
   info["links"]=[html.unescape(x) for x in re.findall(r'(?:href|src)=["\x27]([^"\x27]+)',s,re.I) if any(t in x.lower() for t in [".pdf","tenders","sitemap","rss"])][:10]
 except Exception as exc:
  info["error"]=str(exc)[:200]
 return info
def main():
 out={"checked_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"results":{}}
 for name,url in SITES.items():
  r=fetch(name,url)
  out["results"][name]=r
  print(name,json.dumps(r,ensure_ascii=False)[:1000],flush=True)
 Path("official_alternate_paths_report.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":main()
