"""Temporary read-only TASE classification probe.

Print only type/category frequency summaries for fixed known listed issuers,
not security IDs, raw API rows, or secrets.
"""
from collections import Counter
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tase_registry import (
    TaseClient, TYPES, TRADES, classify, items, issuer_id
)

ISSUERS = {
    "604": "Leumi",
    "662": "Hapoalim",
    "695": "Mizrahi",
    "230": "Bezeq",
    "629": "Teva",
    "600": "Israel Electricity",
    "273": "NICE",
}

def main():
    client = TaseClient(os.environ["TASE_API_KEY"], interval=0)
    types = items(client.get(TYPES), "securitiesTypes")
    by_code = {
        str(r.get("securityFullTypeCode") or "").strip():
        (str(r.get("securityMainTypeDesc") or ""),
         str(r.get("securityTypeDesc") or ""))
        for r in types
    }
    rows = items(client.get(TRADES + "/2026/11/20"), "tradeSecuritiesList")
    results = {}
    for issuer, label in ISSUERS.items():
        counts = Counter()
        for r in rows:
            if issuer_id(r.get("issuerId")) != issuer:
                continue
            code = str(r.get("securityFullTypeCode") or "")
            main, detail = by_code.get(code, ("", ""))
            detected = classify(main + " " + detail)
            counts[(code, main[:60], detail[:80], detected or "not-classified")] += 1
        results[label] = [
            {"code": code, "main_type": main, "subtype": detail,
             "classification": classification, "count": count}
            for (code, main, detail, classification), count in counts.items()
        ]
    type_catalog = [
        {"code": code, "main_type":main, "subtype":detail,
         "classification": classify(main + " " + detail) or "not-classified"}
        for code, (main, detail) in sorted(by_code.items())
    ]
    print(json.dumps({"date": "2026-11-20", "type_catalog": type_catalog,
                      "sample_issuer_type_counts": results},
                     ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
