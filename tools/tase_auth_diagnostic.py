"""Non-sensitive gateway diagnostic for TASE DataWise authentication.

Never prints API keys, credential fingerprints, response bodies or request headers.
Only calls two public, documented official TASE Securities-Basic endpoints.
"""
import json
import os
import re
from urllib import request, error

BASE = "https://datawise.tase.co.il"
ROUTES = {
    "companies-list": "/v1/basic-securities/companies-list",
    "securities-types": "/v1/basic-securities/securities-types",
    # Control: official Basic Indices endpoint; no subscription assumed.
    "indices-control": "/api/v2/basic-indices/indices-list",
}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def diagnostic(url, token=None):
    headers = {"Accept": "application/json", "accept-language": "he-IL"}
    if token is not None:
        headers["apikey"] = token
    req = request.Request(url, headers=headers, method="GET")
    op = request.build_opener(request.ProxyHandler({}), NoRedirect())
    try:
        with op.open(req, timeout=15) as response:
            return {"status": response.status,
                    "auth_challenge": bool(response.headers.get("WWW-Authenticate"))}
    except error.HTTPError as exc:
        return {"status": exc.code,
                "auth_challenge": bool(exc.headers.get("WWW-Authenticate"))}
    except (error.URLError, TimeoutError):
        return {"status": "connection_error"}


def main():
    names = ("TASE_API_KEY", "NEWSR")
    raw = {n: os.environ.get(n, "") for n in names}
    values = {n: v.strip() for n, v in raw.items() if v.strip()}
    print("Credential diagnostics (no values printed):")
    print(json.dumps({
        "present": {n: bool(raw[n]) for n in names},
        "looks_like_uuid": {
            n: bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", values.get(n, "")))
            for n in names
        },
        "outer_whitespace_detected": {n: raw[n] != raw[n].strip() for n in names},
        "same_secret": bool(values.get(names[0]) and values.get(names[0]) == values.get(names[1])),
    }, ensure_ascii=False))
    results = {}
    for label, route in ROUTES.items():
        url = BASE + route
        results[label] = {"no_key": diagnostic(url)}
        for n, value in values.items():
            results[label][n] = diagnostic(url, value)
    print("Official TASE GET response codes and auth-challenge presence only:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    if not values:
        raise SystemExit("No credentials present")


if __name__ == "__main__":
    main()
