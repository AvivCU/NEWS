#!/usr/bin/env python3
"""Live exhaustive name/ID consistency and 10k-event NEWS sidecar stress test.

No TASE raw company names/security rows leave the ephemeral Actions runner.
"""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tase_registry import PreparedRegistry, corp_id, decide, exact_names, read
from tase_procurement_screen import enrich


def audit(obj):
    lookup = PreparedRegistry(obj)
    if not lookup.validation[0]:
        raise ValueError("Registry unusable")
    by_issuer = {}
    for row in obj["rows"]:
        by_issuer.setdefault(row["issuer_id"], row)
    name_aliases = 0
    matches = 0
    ambiguous = 0
    corporate_ids = 0
    for issuer_id, row in by_issuer.items():
        cid = row["corporate_id"]
        if cid and corp_id(cid):
            got = lookup.decide(corporate_id=cid)
            if got["status"] != "ברשימה" or not issuer_id in got["issuer_ids"]:
                raise ValueError("A listed issuer corporate ID did not identify its issuer")
            corporate_ids += 1
        for alias in exact_names(row):
            members = lookup.by_name.get(alias, [])
            owner_set = {record["issuer_id"] for record in members}
            if issuer_id not in owner_set:
                raise ValueError("An official alias failed to appear in its own lookup index")
            got = lookup.decide(name=alias)
            if got["status"] != "ברשימה" or got["auto_disqualify"] or not got["requires_review"]:
                raise ValueError("An official name was not found safely")
            if len(owner_set) > 1:
                if got["match_method"] != "ambiguous_exact_name":
                    raise ValueError("Name collision was not flagged")
                ambiguous += 1
            else:
                if issuer_id not in got["issuer_ids"]:
                    raise ValueError("Named issuer mismatch")
                if got["type"] not in ("מניה", 'אג"ח', "שניהם"):
                    raise ValueError("Unclassified named issuer")
                matches += 1
            # Verify optimized bulk lookups preserve baseline behavior.
            baseline = decide(obj, name=alias)
            if got != baseline:
                raise ValueError("Optimized name matching is not equivalent to reference decision")
            name_aliases += 1

    start = perf_counter()
    events = {"kinds": {"tenders": {"status": "synthetic",
        "events": [
            {"event_id": str(n), "winners": [f"599{n:06d}|ספק סימולציה {n}"]}
            for n in range(10000)
        ],
    }}}
    new = enrich(events, obj)
    elapsed = perf_counter() - start
    report = new["tase_enrichment"]["summary"]
    if report["events_total"] != 10000 or report["winners_total"] != 10000:
        raise ValueError("Stress test dropped procurement events")
    if report["events_all_winners_exact_id_match"] != 0:
        raise ValueError("Stress test wrongly excluded unknown companies")
    if report["winners_not_found"] != 10000:
        raise ValueError("Synthetic unknown company treated as listed")
    if len(new["kinds"]["tenders"]["events"]) != 10000:
        raise ValueError("Event count mutated")
    if len(events["kinds"]["tenders"]["events"]) != 10000:
        raise ValueError("Source mutated")
    return {
        "status": "PASS",
        "all_positive_issuer_records": len(by_issuer),
        "issuer_corporate_id_lookups": corporate_ids,
        "name_alias_lookups": name_aliases,
        "unambiguous_alias_lookups": matches,
        "ambiguous_alias_reviews": ambiguous,
        "bulk_vs_regular_name_results_equal": True,
        "stress_10000_synthetic_events_preserved": True,
        "stress_10000_unknown_not_excluded": True,
        "stress_elapsed_seconds": round(elapsed, 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(read(args.registry)), ensure_ascii=False))


if __name__ == "__main__":
    main()
