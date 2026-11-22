"""Public read-only connectivity probe. No private inputs or credentials."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SOURCES = {
    "innovation_authority": "https://innovationisrael.org.il/invested-companies-2026/",
    "procurement_exemptions": "https://data.gov.il/he/datasets/governmentprocurementadministration/exemptions/65c8fced-c50c-400e-94fb-ef1a208c43e5",
    "procurement_tenders": "https://data.gov.il/he/datasets/governmentprocurementadministration/tenders",
    "emission_permits": "https://data.gov.il/he/datasets/ministry_of_the_environment/permitemissionforzovar",
    "environmental_registry": "https://data.gov.il/he/datasets/ministry_of_the_environment/maflasmultiannualforzover",
    "ourmoney_docs": "https://ourmoneyil.com/api/",
    "iaa_active_tenders": "https://www.iaa.gov.il/tenders-and-contracts/active-tenders/",
}
CUES = {
    "innovation_authority": ("חברות", "השקעה"),
    "procurement_exemptions": ("התקשרות", "פטור"),
    "procurement_tenders": ("מכרז", "רכש"),
    "emission_permits": ("פליטה", "היתר"),
    "environmental_registry": ("מפל", "מפעל"),
    "ourmoney_docs": ("api", "supplier"),
    "iaa_active_tenders": ("ספק", "פטור", "מכרז"),
}
CHALLENGES = ("just a moment", "checking your browser", "access denied", "cf-challenge", "captcha", "attention required")
def classify(status, body, cues):
    content = body[:300000].decode("utf-8", "replace").lower()
    if status in (401, 403, 429, 503) or any(x in content for x in CHALLENGES):
        return "blocked"
    if status >= 400:
        return "http_error"
    if not content.strip():
        return "empty"
    return "content_visible" if any(x.lower() in content for x in cues) else "reachable_unverified"

def run():
    results = []
    for key, url in SOURCES.items():
        row = {"source": key, "url": url}
        try:
            req = Request(url, headers={"User-Agent": "Rosario-Feeds-source-audit/1.0 (read-only)", "Accept": "text/html,application/json,*/*"})
            with urlopen(req, timeout=18) as res:
                body = res.read(500000)
                status = res.status
                row.update(http=status, bytes=len(body), content_type=res.headers.get("Content-Type", ""), final_url=res.geturl())
                row["state"] = classify(status, body, CUES[key])
        except HTTPError as e:
            row.update(http=e.code, state="blocked" if e.code in (401,403,429,503) else "http_error")
        except (URLError, TimeoutError, OSError) as e:
            row.update(state="network_error", error=f"{type(e).__name__}: {str(e)[:160]}")
        results.append(row)
        print(f'{key}: {row["state"]} HTTP={row.get("http", "-")} bytes={row.get("bytes", 0)}', flush=True)
        time.sleep(0.3)
    Path("audit.json").write_text(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "scope": "read-only connectivity, not production", "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
if __name__ == "__main__":
    run()
