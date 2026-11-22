"""Inspect the openly delivered client JavaScript of Israel Railways tender portal.
Report only publicly visible API route names, not response bodies or credentials.
"""
import urllib.request,re,json
from pathlib import Path
BASE="https://tender.rail.co.il"
PATH="/static/js/main.9a87d128_1785151346768.js"
req=urllib.request.Request(BASE+PATH,headers={"User-Agent":"Rosario official portal technical audit"})
with urllib.request.urlopen(req,timeout=50) as r:
 content=r.read(12500000).decode("utf8","replace")
 print("JS_HTTP",r.status,"SIZE",len(content),flush=True)
urls=set(re.findall(r'https?://[a-zA-Z0-9.\-/:?=&_%]+',content))
routes=set(re.findall(r'[/][A-Za-z0-9_-]*(?:api|auction|tender|procurement|tenders|auctions)[A-Za-z0-9_/%?&=.\-]*',content,re.I))
filtered=sorted(u for u in urls if any(s in u.lower() for s in ["rail.co.il","tender","auction","/api/"]))
print("PUBLIC_ENDPOINT_CANDIDATES",json.dumps(filtered[:75],ensure_ascii=False),flush=True)
print("PUBLIC_ROUTE_CANDIDATES",json.dumps(sorted(routes)[:180],ensure_ascii=False),flush=True)
for needle in ["generalauctions","GeneralAuctions","apiurl","apiUrl","baseURL","tenders","auctions","GetAuctions","getAuctions"]:
 i=content.find(needle)
 if i>=0:
  snippet=content[max(0,i-100):i+220]
  # Avoid printing keys/tokens/strings that are unrelated to routing.
  snippet=re.sub(r'(?i)(password|secret|token|key)(.{0,100})',r'\1=[redacted]',snippet)
  print("ROUTE_CONTEXT",needle,snippet[:320],flush=True)
Path("rail_public_js_discovery.json").write_text(json.dumps({"size":len(content),"urls":filtered[:100],"routes":sorted(routes)[:200]},ensure_ascii=False,indent=2),encoding="utf8")
