#!/usr/bin/env python3
"""Rosario TASE exclusion registry.

Official TASE DataWise Securities-Basic data only; read-only except its local
JSON output. Positive issuer-linked evidence is enough for exclusion; absence
from a historical TRADE list never proves a company private or unlisted.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unicodedata
from urllib import error, parse, request

SCHEMA = 1
ORIGIN = "https://datawise.tase.co.il"
COMPANIES = "/v1/basic-securities/companies-list"
TYPES = "/v1/basic-securities/securities-types"
TRADES = "/v1/basic-securities/trade-securities-list"
COMPANIES_URL = "https://market.tase.co.il/he/market_data/tase-companies/public"
SECURITIES_URL = "https://market.tase.co.il/he/market_data/securities/info/all?cl1=0&dType=1"
DEFAULT_FILE = Path("data/latest/tase_registered_securities.json")
MAX_BYTES = 25_000_000
MAX_ROWS = 250_000
UTC = timezone.utc


class SourceError(RuntimeError):
    """Official source unavailable, incomplete or invalid."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # An apikey must never be forwarded to a different host.
        return None


def now_utc() -> datetime:
    return datetime.now(UTC)


def stamp() -> str:
    return now_utc().isoformat(timespec="seconds")


def corp_id(value) -> str:
    s = str(value or "").strip().replace("-", "").replace(" ", "")
    return s if re.fullmatch(r"[0-9]{9}", s) else ""


def issuer_id(value) -> str:
    s = str(value or "").strip()
    return s if re.fullmatch(r"[0-9]{1,10}", s) else ""


def security_id(value) -> str:
    s = str(value or "").strip()
    return s if re.fullmatch(r"[0-9]{4,12}", s) else ""


def name_key(value) -> str:
    s = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"[a-z0-9\u05d0-\u05ea]+", s))


def match_name_key(value) -> str:
    """Normalize punctuation and Hebrew Ltd abbreviation, not distinct names."""
    words = name_key(value).split()
    out = []
    i = 0
    while i < len(words):
        if i + 1 < len(words) and words[i] == "בע" and words[i + 1] == "מ":
            out.append("בעמ")
            i += 2
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


NAME_FIELDS = ("name_he", "name_en", "name_full_he", "name_full_en")


def exact_names(record):
    return {match_name_key(record.get(field, "")) for field in NAME_FIELDS} - {""}


def items(payload, section):
    if not isinstance(payload, dict):
        raise SourceError(f"{section}: invalid root")
    value = payload.get(section)
    if value is None and isinstance(payload.get("data"), dict):
        value = payload["data"].get(section)
    if not isinstance(value, dict) or not isinstance(value.get("result"), list):
        raise SourceError(f"{section}: missing result list")
    out = value["result"]
    if (not out or len(out) > MAX_ROWS or
            any(not isinstance(x, dict) for x in out)):
        raise SourceError(f"{section}: empty/invalid result list")
    if isinstance(value.get("total"), int) and value["total"] != len(out):
        raise SourceError(f"{section}: truncated result list")
    return out


def classify(label) -> str:
    """Conservative fallback only when the official four-digit type code is absent."""
    s = name_key(label)
    if not s:
        return ""
    forbidden = ("ממשלתי", "ממשלתיות", "מלווה קצר", "מקמ", "treasury",
                 "government", "sovereign", "etf", "קרן סל", "תעודת סל",
                 "תעודות סל", "קרנות נאמנות", "קרן חוץ", "קרן השקעה",
                 "mutual fund", "fund", "option", "אופציה", "זכות",
                 "warrant", "index", "מדד", "ניירות ערך מסחריים",
                 "ני ע מסחריים", "commercial paper", "תעודות פקדון")
    if any(x in s for x in forbidden):
        return ""
    if any(x in s for x in ("אג ח קונצרני", "אג ח חברות", "אגח קונצרני",
                            "אגח חברות", "אג ח להמרה", "אגח להמרה",
                            "איגרות חוב", "אגרות חוב", "corporate bond",
                            "convertible bond", "debenture")):
        return "אג\"ח"
    if any(x in s for x in ("מניה", "מנית", "מניות",
                            "ordinary share", "common share",
                            "ordinary stock", "common stock", "shares")):
        return "מניה"
    return ""


# The official Securities Types endpoint (verified 2026-11-23) uses numeric
# four-digit securityFullTypeCode. Strictly allowlist observed categories;
# unknown codes are UNCLASSIFIED, never silently treated as listed shares/bonds.
# 0104 is Leumi's stock share. 0113 is a closed mutual fund, NOT stock.
# Exclude debt-looking 0504/0506/0508/0512 (tracking/deposit certificate,
# commercial paper, debt participation) from corporate bonds.
OFFICIAL_STOCK_CODES = frozenset((
    "0101", "0102", "0103", "0104", "0105", "0106", "0107",
    "0108", "0109", "0110", "0111", "0112", "0114", "0198", "0199",
))
OFFICIAL_CORPORATE_BOND_CODES = frozenset((
    "0301", "0302", "0303", "0304", "0305", "0306",
    "0501", "0502", "0503", "0505", "0507",
    "0509", "0510", "0511", "0513", "0514",
))


def classify_code(code, label="") -> str:
    code = str(code or "").strip()
    if code in OFFICIAL_STOCK_CODES:
        return "מניה"
    if code in OFFICIAL_CORPORATE_BOND_CODES:
        return "אג\"ח"
    if re.fullmatch(r"[0-9]{4}", code):
        return ""
    # Deterministic synthetic tests and verified operator exports may supply
    # descriptive non-numeric categories; don't override an official code.
    return classify(label)


class TaseClient:
    """HTTPS GET-only allowlist; no redirects, proxies or browser automation."""
    def __init__(self, api_key: str, opener=None, interval=0.25):
        if not api_key.strip():
            raise SourceError("TASE_API_KEY missing; no official refresh performed")
        self._key = api_key.strip()
        self._open = opener or request.build_opener(request.ProxyHandler({}), NoRedirect()).open
        self.interval = interval

    def get(self, path: str, language="he-IL"):
        permitted = (COMPANIES, TYPES)
        date_path = re.fullmatch(r"/v1/basic-securities/trade-securities-list/\d{4}/\d{1,2}/\d{1,2}", path)
        if path not in permitted and not date_path:
            raise ValueError("Endpoint is not on the allowlist")
        if language not in ("he-IL", "en-US"):
            raise ValueError("Invalid language")
        req = request.Request(ORIGIN + path, headers={
            "Accept": "application/json", "Accept-Language": language,
            "apikey": self._key, "User-Agent": "RosarioTaseRegistry/1.0",
        })
        time.sleep(self.interval)
        try:
            with self._open(req, timeout=25) as response:
                final_url = response.geturl() if hasattr(response, "geturl") else req.full_url
                if final_url != req.full_url:
                    raise SourceError("Unexpected redirect from official endpoint")
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise SourceError("Oversized official API response")
            obj = json.loads(raw.decode("utf-8-sig"))
            if not isinstance(obj, dict):
                raise SourceError("Unexpected official API response")
            return obj
        except error.HTTPError as exc:
            if exc.code in (401, 403, 429):
                raise SourceError(f"TASE access denied/rate-limited (HTTP {exc.code}); stopped") from None
            raise SourceError(f"TASE HTTP {exc.code}; stopped") from None
        except (error.URLError, TimeoutError):
            raise SourceError("TASE connection unavailable; stopped") from None
        except (UnicodeError, json.JSONDecodeError):
            raise SourceError("TASE returned invalid JSON; stopped") from None


def collect(client: TaseClient, lookback=28, today=None):
    """Date-based trades give positive matches, NOT the full registered universe."""
    if not 7 <= lookback <= 45:
        raise ValueError("lookback must be within 7..45 days")
    today = today or now_utc().date()
    heb = items(client.get(COMPANIES), "companiesList")
    types = items(client.get(TYPES), "securitiesTypes")
    if len(heb) < 50 or len(types) < 2:
        raise SourceError("Implausibly small companies/types response")
    try:
        eng = items(client.get(COMPANIES, "en-US"), "companiesList")
    except SourceError:
        eng = []
    observed = {}
    dates = []
    empty = []
    for offset in range(lookback):
        day = today - timedelta(days=offset)
        # TASE trading week has been Mon-Fri since 2026-01-05.
        if day >= date(2026, 1, 5) and day.weekday() in (5, 6):
            continue
        endpoint = f"{TRADES}/{day.year}/{day.month}/{day.day}"
        try:
            rows = items(client.get(endpoint), "tradeSecuritiesList")
        except SourceError as exc:
            # Historical holidays may not have an API resource (404). All
            # auth/WAF/429/5xx problems abort the refresh instead of bypassing.
            if "HTTP 404" not in str(exc) and "empty/invalid result" not in str(exc):
                raise
            empty.append(day.isoformat())
            continue
        dates.append(day.isoformat())
        for row in rows:
            sid = security_id(row.get("securityId"))
            if sid:
                record = dict(row)
                record["_observed_on"] = day.isoformat()
                record["_source_endpoint"] = endpoint
                observed.setdefault(sid, record)
    if len(dates) < 5 or len(observed) < 200:
        raise SourceError("Too little official trade coverage; snapshot unchanged")
    return {
        "companies_he": heb, "companies_en": eng, "types": types,
        "securities": list(observed.values()),
        "source_as_of": max(dates),
        "coverage": {
            "kind": "observed_trades_positive_only",
            "complete_registered_securities": False,
            "lookback_days": lookback,
            "observed_dates": sorted(dates),
            "dates_without_records": sorted(empty),
        },
    }


def build(data, at=None):
    at = at or stamp()
    he, en = {}, {}
    for record in data["companies_he"]:
        iid = issuer_id(record.get("issuerId"))
        if iid and str(record.get("companyName") or "").strip():
            if iid in he:
                raise SourceError("Duplicate official issuer ID")
            he[iid] = {
                "issuer_id": iid, "corporate_id": corp_id(record.get("corporateId")),
                "name_he": str(record["companyName"]).strip(), "name_en": "",
                "name_full_he": str(record.get("companyFullName") or "").strip(),
                "name_full_en": "",
            }
    for record in data["companies_en"]:
        iid = issuer_id(record.get("issuerId"))
        if iid in he:
            he[iid]["name_en"] = str(record.get("companyName") or "").strip()
            he[iid]["name_full_en"] = str(record.get("companyFullName") or "").strip()
    if len(he) < 1:
        raise SourceError("No official companies in source")
    cid_owners = {}
    for iid, company in he.items():
        cid = company["corporate_id"]
        if cid:
            cid_owners.setdefault(cid, set()).add(iid)
    by_cid = {cid: next(iter(owners)) for cid, owners in cid_owners.items()
              if len(owners) == 1}
    types = {}
    for entry in data["types"]:
        code = str(entry.get("securityFullTypeCode") or "").strip()
        if code:
            types[code] = " ".join([
                str(entry.get("securityMainTypeDesc") or ""),
                str(entry.get("securityTypeDesc") or ""),
            ])
    companies = {}
    excluded = unresolved = conflicts = 0
    for row in data["securities"]:
        sid = security_id(row.get("securityId"))
        code = str(row.get("securityFullTypeCode") or "").strip()
        category = classify_code(code, types.get(code) or row.get("securityTypeDesc") or "")
        if not category:
            excluded += 1
            continue
        iid = issuer_id(row.get("issuerId"))
        cid = corp_id(row.get("corporateId"))
        known_iid = iid if iid in he else ""
        known_cid = by_cid.get(cid, "") if cid else ""
        if (known_iid and cid and he[known_iid]["corporate_id"] and
                he[known_iid]["corporate_id"] != cid) or (
                known_cid and iid and iid != known_cid):
            conflicts += 1
            continue
        owner = known_iid or known_cid
        if not sid or not owner:
            unresolved += 1
            continue
        rec = {
            **he[owner], "security_id": sid, "security_type": category,
            "security_name": str(row.get("securityName") or "").strip(),
            "isin": str(row.get("isin") or "").strip(),
            "observed_on": str(row.get("_observed_on") or ""),
            "updated_at": at, "source_url": SECURITIES_URL,
            "source_api_url": ORIGIN + str(row.get("_source_endpoint") or ""),
        }
        companies.setdefault(owner, {})[sid] = rec
    if not companies:
        raise SourceError("No issuer-linked official shares/bonds; snapshot unchanged")
    all_rows = []
    for securities in companies.values():
        labels = {r["security_type"] for r in securities.values()}
        kind = "שניהם" if len(labels) == 2 else next(iter(labels))
        for entry in securities.values():
            entry["type"] = kind
            all_rows.append(entry)
    all_rows.sort(key=lambda r: (r["corporate_id"], r["issuer_id"], r["security_id"]))
    return {
        "schema_version": SCHEMA, "last_updated": at,
        "source_as_of": data.get("source_as_of"),
        "last_attempt_at": at, "run_status": "success", "last_error": None,
        "row_count": len(all_rows), "issuer_count": len(companies),
        "source": {
            "provider": "Official Tel Aviv Stock Exchange / DataWise",
            "companies": COMPANIES_URL, "securities": SECURITIES_URL,
            "api": ORIGIN,
        },
        "coverage": data["coverage"],
        "diagnostics": {
            "source_companies": len(he),
            "observed_securities": len(data["securities"]),
            "excluded_non_equity_or_non_corporate_debt": excluded,
            "unlinked_securities": unresolved,
            "conflicting_identifiers": conflicts,
        },
        "rows": all_rows,
    }


def validate(obj, now=None, days=10, stale=True):
    if not isinstance(obj, dict) or obj.get("schema_version") != SCHEMA:
        return False, "חסר קובץ תקין או גרסת סכמה מוכרת"
    rows = obj.get("rows")
    if (not isinstance(rows, list) or not isinstance(obj.get("row_count"), int) or
            len(rows) != obj["row_count"] or len(rows) > MAX_ROWS):
        return False, "רשומות חסרות או מספר שורות שגוי"
    if obj.get("run_status") not in ("success", "failed"):
        return False, "סטטוס ריצה לא תקין"
    at = obj.get("last_updated")
    if not at:
        return False, "עדיין אין ריצה מוצלחת ממקור רשמי"
    try:
        parsed = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("naive timestamp")
    except (ValueError, TypeError, AttributeError):
        return False, "תאריך עדכון פגום"
    current = now or now_utc()
    if parsed > current + timedelta(hours=1):
        return False, "תאריך עדכון בעתיד"
    if stale and current - parsed > timedelta(days=days):
        return False, "הקובץ ישן מ-10 ימים"
    source_as_of = obj.get("source_as_of")
    if stale:
        try:
            src_day = date.fromisoformat(source_as_of)
            if (current.date() - src_day).days > days or src_day > current.date() + timedelta(days=1):
                raise ValueError()
        except (ValueError, TypeError):
            return False, "תאריך נתוני המקור חסר או ישן"
    if not rows:
        return False, "לא נמצאו שורות ממקור רשמי"
    seen = set()
    mandatory = ("issuer_id", "corporate_id", "name_he", "name_en",
                 "name_full_he", "name_full_en", "security_id",
                 "security_type", "type", "source_url", "updated_at")
    for row in rows:
        if not isinstance(row, dict) or any(k not in row for k in mandatory):
            return False, "רשומה פגומה"
        if (not issuer_id(row["issuer_id"]) or not security_id(row["security_id"]) or
                (row["corporate_id"] and not corp_id(row["corporate_id"])) or
                not isinstance(row["name_he"], str) or not row["name_he"].strip() or
                not isinstance(row["name_en"], str) or
                not isinstance(row["name_full_he"], str) or
                not isinstance(row["name_full_en"], str) or
                row["security_type"] not in ("מניה", "אג\"ח") or
                row["type"] not in ("מניה", "אג\"ח", "שניהם") or
                row["source_url"] != SECURITIES_URL):
            return False, "ערכי רשומה לא תקינים"
        key = (row["issuer_id"], row["security_id"])
        if key in seen:
            return False, "רשומה כפולה"
        seen.add(key)
    return True, ""


def _decide_core(obj, name="", corporate_id="", now=None, *, validation=None, candidate_rows=None):
    good, reason = validation if validation is not None else validate(obj, now=now)
    if not good:
        return {"status": "לא ניתן לקבוע", "auto_disqualify": False,
                "requires_review": False, "reason": reason,
                "last_updated": obj.get("last_updated") if isinstance(obj, dict) else None}
    cid = corp_id(corporate_id)
    if corporate_id and not cid:
        return {"status": "לא ברשימה", "auto_disqualify": False,
                "requires_review": True, "reason": "ח.פ. לא תקין; יש לבדוק",
                "last_updated": obj["last_updated"]}
    normalized = match_name_key(name)
    rows = obj["rows"] if candidate_rows is None else candidate_rows
    found_id = [r for r in rows if cid and r["corporate_id"] == cid]
    found_name = [r for r in rows if normalized and normalized in exact_names(r)]
    if found_id:
        matches = found_id
        method = "exact_corporate_id"
        distinct_names = {name_key(r["name_he"]) for r in matches}
        # Corporate ID is primary; disagreeing input name needs human review.
        mismatched_name = bool(normalized and not any(
            normalized in exact_names(r) for r in matches
        ))
        review = len({r["issuer_id"] for r in matches}) != 1 or len(distinct_names) != 1 or mismatched_name
    elif found_name:
        matches, method, review = found_name, "exact_name_only", True
    else:
        return {"status": "לא ברשימה", "auto_disqualify": False,
                "requires_review": False,
                "reason": "לא נמצא ברשימה; אין בכך הוכחה לחברה פרטית",
                "last_updated": obj["last_updated"], "source": SECURITIES_URL}
    issuers = {r["issuer_id"] for r in matches}
    if len(issuers) != 1 and method == "exact_name_only":
        return {
            "status": "ברשימה", "type": "לא חד-משמעי",
            "auto_disqualify": False, "requires_review": True,
            "match_method": "ambiguous_exact_name",
            "reason": "שם זהה מופיע אצל כמה מנפיקים; יש לאמת ח.פ. לפני סיווג",
            "issuer_count": len(issuers), "last_updated": obj["last_updated"],
            "source": SECURITIES_URL,
        }
    types = {r["security_type"] for r in matches}
    category = "שניהם" if len(types) == 2 else next(iter(types))
    verified = method == "exact_corporate_id" and not review
    # Equity listing excludes. A corporate bond alone reduces priority,
    # but does NOT disqualify a prospect from advisory/M&A coverage.
    has_equity = "מניה" in types
    has_bonds = 'אג"ח' in types
    auto = verified and has_equity
    bond_alert = verified and has_bonds
    return {
        "status": "ברשימה", "type": category, "auto_disqualify": auto,
        "requires_review": review, "match_method": method,
        "equity_listed_confirmed": bool(auto),
        "corporate_bond_confirmed": bool(bond_alert),
        "scoring_signal": "strong_negative" if bond_alert else None,
        "reason": ("נפסלה – מניות החברה נסחרות בבורסה" if auto else
                   'התראת אג"ח קונצרני – להפחית ניקוד, לא לפסול' if bond_alert else
                   "התאמת שם/מזהה לא חד-משמעית – דורש בדיקה"),
        "name_he": matches[0]["name_he"], "name_en": matches[0]["name_en"],
        "name_full_he": matches[0]["name_full_he"],
        "name_full_en": matches[0]["name_full_en"],
        "corporate_id": matches[0]["corporate_id"],
        "issuer_ids": sorted({r["issuer_id"] for r in matches}),
        "security_ids": sorted({r["security_id"] for r in matches}),
        "bond_series": sorted({r["security_name"] for r in matches
                              if r["security_type"] == "אג\"ח" and r.get("security_name")}),
        "source": SECURITIES_URL, "last_updated": obj["last_updated"],
        "source_run_status": obj["run_status"],
        "warning": "הרענון האחרון נכשל; נעשה שימוש במידע האחרון התקין"
                   if obj["run_status"] == "failed" else None,
    }


def decide(obj, name="", corporate_id="", now=None):
    """Single-company lookup; validation and all matches checked afresh."""
    return _decide_core(obj, name=name, corporate_id=corporate_id, now=now)


class PreparedRegistry:
    """Safe O(1) shortlist for bulk screening; validate snapshot only once.

    Uses exactly the same lookup policy and response formatter as decide().
    Neither an invalid source nor a missing ID can cause auto-disqualification.
    """
    def __init__(self, obj, now=None):
        self.obj = obj
        self.validation = validate(obj, now=now)
        self.by_id = {}
        self.by_name = {}
        if self.validation[0]:
            for row in obj["rows"]:
                cid = row["corporate_id"]
                if cid:
                    self.by_id.setdefault(cid, []).append(row)
                for key in exact_names(row):
                    self.by_name.setdefault(key, []).append(row)

    def decide(self, name="", corporate_id=""):
        cid = corp_id(corporate_id)
        key = match_name_key(name)
        matched = self.by_id.get(cid, ()) if cid else ()
        if not matched:
            matched = self.by_name.get(key, ()) if key else ()
        return _decide_core(
            self.obj, name=name, corporate_id=corporate_id,
            validation=self.validation, candidate_rows=matched,
        )


def read(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Snapshot file too large")
    return json.loads(path.read_text(encoding="utf-8"))


def lookup(path=DEFAULT_FILE, *, name="", corporate_id="", now=None):
    try:
        return decide(read(path), name=name, corporate_id=corporate_id, now=now)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return {"status": "לא ניתן לקבוע", "auto_disqualify": False,
                "requires_review": False, "reason": "קובץ חסר או פגום",
                "last_updated": None}


def atomic_save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".tase-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def mark_failed(path, message):
    try:
        existing = read(path)
        if not validate(existing, stale=False)[0]:
            raise ValueError("Corrupt prior snapshot")
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        existing = {
            "schema_version": SCHEMA, "last_updated": None,
            "source_as_of": None, "row_count": 0, "issuer_count": 0,
            "source": {"provider": "Official TASE", "companies": COMPANIES_URL,
                       "securities": SECURITIES_URL, "api": ORIGIN},
            "coverage": {"kind": "no_successful_official_fetch"}, "rows": [],
        }
    existing.update({"run_status": "failed", "last_attempt_at": stamp(),
                     "last_error": str(message)[:160]})
    atomic_save(path, existing)


def refresh(path=DEFAULT_FILE, lookback=28, client=None):
    try:
        client = client or TaseClient(os.environ.get("TASE_API_KEY", ""))
        data = collect(client, lookback=lookback)
        obj = build(data)
        if obj["row_count"] < 100 or obj["issuer_count"] < 30:
            raise SourceError("Too few confidently linked securities/issuers; refusing partial source")
        valid, reason = validate(obj)
        if not valid:
            raise SourceError(f"Built file failed validation: {reason}")
        atomic_save(path, obj)
        print(json.dumps({"status": "success", "rows": obj["row_count"],
                          "issuers": obj["issuer_count"],
                          "source_as_of": obj["source_as_of"]}, ensure_ascii=False))
        return 0
    except (SourceError, ValueError) as exc:
        mark_failed(path, str(exc))
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


def _field(row, aliases):
    normalized = {name_key(k): v for k, v in row.items()}
    return next((str(normalized.get(name_key(n)) or "").strip()
                 for n in aliases if str(normalized.get(name_key(n)) or "").strip()), "")


def manual_csv(path, category):
    """Operator-attested official CSV only. Never infer issuer from bond name."""
    if path.stat().st_size > MAX_BYTES:
        raise SourceError("Manual CSV too large")
    data = path.read_bytes()
    decoded = None
    for enc in ("utf-8-sig", "utf-16", "cp1255"):
        try:
            decoded = data.decode(enc)
            break
        except UnicodeError:
            continue
    if decoded is None or "<html" in decoded[:120].lower():
        raise SourceError("CSV unreadable or an HTML/login page")
    try:
        dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    table = list(csv.DictReader(io.StringIO(decoded), dialect=dialect))
    if not table or len(table) > MAX_ROWS or any(None in r for r in table):
        raise SourceError("Manual CSV empty or malformed")
    result = []
    for row in table:
        if any(len(str(v or "")) > 4096 for v in row.values()):
            raise SourceError("Oversized CSV cell")
        if category == "companies":
            result.append({
                "companyName": _field(row, ("companyName", "שם חברה", "שם החברה", "שם")),
                "issuerId": _field(row, ("issuerId", "מספר מנפיק")),
                "corporateId": _field(row, ("corporateId", "מספר תאגיד", "חפ", "ח.פ.")),
            })
        elif category == "types":
            result.append({
                "securityFullTypeCode": _field(row, ("securityFullTypeCode", "קוד סוג נייר")),
                "securityTypeDesc": _field(row, ("securityTypeDesc", "סוג נייר", "סוג ני\"ע")),
            })
        else:
            result.append({
                "securityId": _field(row, ("securityId", "מספר נייר", "מספר ני\"ע", "מס ני\"ע")),
                "issuerId": _field(row, ("issuerId", "מספר מנפיק")),
                "corporateId": _field(row, ("corporateId", "מספר תאגיד", "חפ", "ח.פ.")),
                "securityName": _field(row, ("securityName", "שם נייר", "שם ני\"ע", "שם (עברית)")),
                "securityFullTypeCode": _field(row, ("securityFullTypeCode", "קוד סוג נייר")),
                "securityTypeDesc": _field(row, ("securityTypeDesc", "סוג נייר", "סוג ני\"ע (עברית)")),
                "isin": _field(row, ("isin", "ISIN")),
            })
    return result


def refresh_manual(path, company_file, security_file, source_date, type_file=None, english_file=None):
    """No scraping or bypass. Operator must expressly attest source provenance."""
    try:
        age = (now_utc().date() - source_date).days
        if not 0 <= age <= 10:
            raise SourceError("Manual TASE export date invalid or older than 10 days")
        companies_he = manual_csv(company_file, "companies")
        companies_en = manual_csv(english_file, "companies") if english_file else []
        securities = manual_csv(security_file, "securities")
        types = manual_csv(type_file, "types") if type_file else []
        for s in securities:
            s["_observed_on"] = source_date.isoformat()
            s["_source_endpoint"] = ""
        obj = build({
            "companies_he": companies_he, "companies_en": companies_en,
            "types": types, "securities": securities,
            "source_as_of": source_date.isoformat(),
            "coverage": {
                "kind": "operator_attested_official_export",
                "complete_registered_securities": False,
                "independently_verified": False,
                "note": "manual CSV provenance and coverage must be confirmed by operator",
            },
        })
        valid, reason = validate(obj)
        if not valid:
            raise SourceError(reason)
        atomic_save(path, obj)
        print(json.dumps({"status": "success", "rows": obj["row_count"],
                          "note": "OPERATOR-ATTESTED, NOT INDEPENDENTLY VERIFIED"}, ensure_ascii=False))
        return 0
    except (SourceError, ValueError, OSError, UnicodeError) as exc:
        mark_failed(path, str(exc))
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rosario official TASE exclusion registry")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("refresh", help="Fetch official DataWise; needs TASE_API_KEY")
    p.add_argument("--output", type=Path, default=DEFAULT_FILE)
    p.add_argument("--lookback", type=int, default=28)
    p = sub.add_parser("refresh-manual", help="Import operator-attested official TASE CSVs")
    p.add_argument("--official-source-attested", action="store_true", required=True)
    p.add_argument("--companies", type=Path, required=True)
    p.add_argument("--securities", type=Path, required=True)
    p.add_argument("--types", type=Path)
    p.add_argument("--english", type=Path)
    p.add_argument("--source-date", type=date.fromisoformat, required=True)
    p.add_argument("--output", type=Path, default=DEFAULT_FILE)
    p = sub.add_parser("lookup", help="Print exactly one of three states and evidence")
    p.add_argument("--registry", type=Path, default=DEFAULT_FILE)
    p.add_argument("--name", default="")
    p.add_argument("--corporate-id", default="")
    p = sub.add_parser("stats")
    p.add_argument("--registry", type=Path, default=DEFAULT_FILE)
    args = parser.parse_args(argv)
    if args.command == "refresh":
        return refresh(args.output, args.lookback)
    if args.command == "refresh-manual":
        return refresh_manual(args.output, args.companies, args.securities,
                              args.source_date, args.types, args.english)
    if args.command == "lookup":
        if not (args.name or args.corporate_id):
            parser.error("Supply --name or --corporate-id")
        print(json.dumps(lookup(args.registry, name=args.name,
                                corporate_id=args.corporate_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "stats":
        try:
            obj = read(args.registry)
            fields = ("run_status", "last_updated", "source_as_of", "last_attempt_at",
                      "last_error", "row_count", "issuer_count", "source", "coverage", "diagnostics")
            report = {key: obj.get(key) for key in fields}
            report["usable"] = validate(obj)[0]
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            report = {"usable": False, "run_status": "failed", "reason": "missing/corrupt"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
