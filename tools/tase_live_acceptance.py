#!/usr/bin/env python3
"""Read-only acceptance check against freshly fetched official TASE data.

This script prints aggregate metrics and a few hardcoded public-company name
lookup results, not raw licensed securities data or complete company lists.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tase_registry import corp_id, decide, read, validate, now_utc

# Exact corporate identifiers independently obtained from TASE's official
# companies-list response on 2026-11-23; not generated from the snapshot being
# tested. Only checks positive evidence. No negative private-company claim.
KNOWN_LISTED_CORPORATE_IDS = (
    "520031931",  # Bezeq
    "520013954",  # Teva
    "520018078",  # Leumi
    "520000118",  # Bank Hapoalim
    "520000522",  # Mizrahi Tefahot
    "520036872",  # NICE
    "520039413",  # Matrix
    "520037649",  # Castro
    "520038274",  # Aura
    "520038506",  # Alony Hetz
    "520025602",  # Delta Galil
    "520027830",  # ICL
    "520024126",  # Mivne
    "520038225",  # Willy Food
    "520038530",  # Hamat
    "520000472",  # Israel Electric Corporation — bond-only candidate
    "520032046",  # Mizrahi Tefahot Issuances — bond-only candidate
)
BOND_ONLY_CANDIDATES = ("520000472", "520032046")

# Input-name tests deliberately independent of snapshot-derived aliases.
# The tuple's expected corporate ID is our reference for the named issuer.
KNOWN_NAME_CASES = (
    ("בזק", "520031931"),
    ('בזק החברה הישראלית לתקשורת בע"מ', "520031931"),
    ("טבע", "520013954"),
    ('טבע תעשיות פרמצבטיות בע"מ', "520013954"),
    ("לאומי", "520018078"),
    ('בנק לאומי לישראל בע"מ', "520018078"),
    ("פועלים", "520000118"),
    ('בנק הפועלים בע"מ', "520000118"),
    ("מזרחי טפחות", "520000522"),
    ("נייס", "520036872"),
    ("מטריקס", "520039413"),
    ("קסטרו", "520037649"),
    ("אאורה", "520038274"),
    ("אלוני חץ", "520038506"),
    ("דלתא גליל", "520025602"),
    ("חשמל", "520000472"),
    ('חברת החשמל לישראל בע"מ', "520000472"),
    ("מזרחי טפחות הנפ", "520032046"),
    ('מזרחי טפחות חברה להנפקות בע"מ', "520032046"),
    ("חמת", "520038530"),
)



def audit(obj):
    valid, reason = validate(obj)
    if not valid:
        raise ValueError("Registry invalid: " + reason)
    rows = obj["rows"]
    by_issuer = {}
    for row in rows:
        by_issuer.setdefault(row["issuer_id"], []).append(row)
        if row["corporate_id"] and not corp_id(row["corporate_id"]):
            raise ValueError("Invalid corporate ID in official output")

    types_by_issuer = Counter()
    for grouped in by_issuer.values():
        types_by_issuer[grouped[0]["type"]] += 1
        expected_kind = (
            "שניהם" if len({r["security_type"] for r in grouped}) == 2
            else grouped[0]["security_type"]
        )
        if any(r["type"] != expected_kind for r in grouped):
            raise ValueError("Inconsistent company-wide security type")

    found = 0
    missing = 0
    for corporate_id in KNOWN_LISTED_CORPORATE_IDS:
        result = decide(obj, corporate_id=corporate_id)
        if result["status"] == "ברשימה":
            expected_equity = expected == "מניה" or expected == "שניהם"
            expected_bonds = expected == 'אג"ח' or expected == "שניהם"
            if result["auto_disqualify"] != expected_equity or result["requires_review"]:
                raise ValueError("Verified equity decision diverges from expected")
            if bool(result.get("corporate_bond_confirmed")) != expected_bonds:
                raise ValueError("Known corporate ID did not match unambiguously")
            found += 1
        else:
            missing += 1  # A missing security isn't proof of private status.

    if found < 10:
        raise ValueError(f"Too few independent known listed positives: {found}")

    bond_only_found = 0
    for corporate_id in BOND_ONLY_CANDIDATES:
        result = decide(obj, corporate_id=corporate_id)
        if result["status"] == "ברשימה" and result["type"] == 'אג"ח':
            bond_only_found += 1
    if bond_only_found < 1:
        raise ValueError("No independent bond-only issuer verified")

    # Independent factual equity+bond reference checks: Leumi was formerly
    # incorrectly bond-only because code 0104 (stock share) went unclassified.
    for bank_cid in ("520018078", "520000118", "520000522"):
        bank = decide(obj, corporate_id=bank_cid)
        if bank["status"] != "ברשימה" or bank["type"] != "שניהם":
            raise ValueError("Known listed bank has both stock and bonds, but classification disagrees")

    if min(types_by_issuer['אג"ח'], types_by_issuer['מניה'],
           types_by_issuer["שניהם"]) < 1:
        raise ValueError("Missing bond-only, share-only or mixed categories")

    # A user supplies a NAME ONLY: the result must identify the correct
    # issuer and observed share/bond category, while never auto-excluding.
    named_cases_passed = 0
    named_examples = []
    for input_name, expected_corporate_id in KNOWN_NAME_CASES:
        result = decide(obj, name=input_name)
        if (result["status"] != "ברשימה"
                or result["corporate_id"] != expected_corporate_id
                or result["match_method"] != "exact_name_only"
                or not result["requires_review"]
                or result["auto_disqualify"]):
            raise ValueError("Independent named-company lookup failed")
        if expected_corporate_id in BOND_ONLY_CANDIDATES and result["type"] != 'אג"ח':
            raise ValueError("Known bond-only company did not classify as corporate debt")
        named_cases_passed += 1
        if input_name in ("בזק", "טבע", "לאומי", "קסטרו", "חשמל",
                          "מזרחי טפחות הנפ", "מטריקס", "אאורה"):
            named_examples.append({
                "input_name": input_name,
                "result": result["status"],
                "security_type": result["type"],
                "requires_id_verification": result["requires_review"],
            })

    # 10 truly synthetic absent IDs; do not call these real private companies.
    synthetic_negative_checks = 0
    for i in range(10):
        result = decide(obj, corporate_id=str(999000000 + i))
        if result["auto_disqualify"]:
            raise ValueError("Synthetic unknown ID was auto-disqualified")
        synthetic_negative_checks += 1

    first = next(r for r in rows if r["corporate_id"])
    by_name = decide(obj, name=first["name_he"])
    if by_name["auto_disqualify"] or not by_name["requires_review"]:
        raise ValueError("Name-only candidate was auto-disqualified")

    stale_time = now_utc() + timedelta(days=11)
    stale = decide(obj, corporate_id=first["corporate_id"], now=stale_time)
    if stale["status"] != "לא ניתן לקבוע" or stale["auto_disqualify"]:
        raise ValueError("Stale source did not fail closed")

    # No raw response bodies or complete lists are printed; the input examples above are fixed.
    return {
        "result": "PASS",
        "source_companies": obj["diagnostics"]["source_companies"],
        "source_as_of": obj["source_as_of"],
        "observed_securities": obj["diagnostics"]["observed_securities"],
        "classified_security_rows": len(rows),
        "linked_issuers": len(by_issuer),
        "share_only_issuers": types_by_issuer["מניה"],
        "bond_only_issuers": types_by_issuer['אג"ח'],
        "share_and_bond_issuers": types_by_issuer["שניהם"],
        "independent_known_public_positives": found,
        "known_public_not_observed": missing,
        "independent_known_bond_only_positives": bond_only_found,
        "independent_known_banks_with_both": 3,
        "name_only_real_company_cases_passed": named_cases_passed,
        "name_only_examples": named_examples,
        "synthetic_unknown_id_checks": synthetic_negative_checks,
        "name_only_requires_review": True,
        "stale_data_fails_closed": True,
        "incomplete_trading_coverage": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(read(args.registry)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
