#!/usr/bin/env python3
"""Run a small synthetic procurement event envelope against live TASE data.

Read-only, ephemeral and no raw security records printed or committed.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tase_registry import read
from tase_procurement_screen import enrich


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()
    source = {
        "checked_utc": "2026-11-23T00:00:00+00:00",
        "kinds": {"tenders": {
            "status": "synthetic_acceptance",
            "counts": {"new_publication": 7},
            "events": [
                {"publication_id": "demo1", "event_id": "demo-id-1",
                 "winners": ["520031931|בזק"]},
                {"publication_id": "demo2", "event_id": "demo-id-2",
                 "winners": ['|חברת החשמל לישראל בע"מ']},
                {"publication_id": "demo3", "event_id": "demo-id-3",
                 "winners": ["520031931|בזק", "599999999|חברה שלא קיימת"]},
                {"publication_id": "demo4", "event_id": "demo-id-4",
                 "winners": ["|לאומי"]},
                {"publication_id": "demo5", "event_id": "demo-id-5",
                 "winners": ['|מזרחי טפחות חברה להנפקות בע"מ']},
                {"publication_id": "demo6", "event_id": "demo-id-6",
                 "winners": ["599999999|חברה שלא קיימת"]},
                {"publication_id": "demo7", "event_id": "demo-id-7", "winners": []},
            ]
        }}
    }
    prior = copy.deepcopy(source)
    new = enrich(source, read(args.registry))
    records = new["kinds"]["tenders"]["events"]
    cases = [
        (0, "שניהם", True, False),
        (1, 'אג"ח', False, True),
        (2, "שניהם", False, False),
        (3, "שניהם", False, True),
        (4, 'אג"ח', False, True),
        (5, None, False, False),
        (6, None, False, False),
    ]
    assert new["tase_enrichment"]["status"] == "ready"
    assert source == prior
    assert [x["event_id"] for x in records] == [x["event_id"] for x in prior["kinds"]["tenders"]["events"]]
    for index, expected_type, all_exact, review in cases:
        event = records[index]["tase_screen"]
        assert event["all_winners_exact_id_match"] == all_exact
        if expected_type is not None:
            assert event["winners"][0]["type"] == expected_type
            assert event["winners"][0]["requires_review"] == review
    assert records[5]["tase_screen"]["winners"][0]["status"] == "לא ברשימה"
    assert records[6]["tase_screen"]["classification"] == "no_winners"
    reduced = copy.deepcopy(new)
    reduced.pop("tase_enrichment")
    for e in reduced["kinds"]["tenders"]["events"]:
        e.pop("tase_screen", None)
    assert reduced == prior
    print(json.dumps({
        "status": "PASS",
        "synthetic_procurement_events_checked": len(records),
        "all_original_event_ids_and_contents_retained": True,
        "positive_short_and_legal_name_lookup": True,
        "mixed_supplier_never_excluded": True,
        "name_only_never_auto_disqualified": True,
    }))


if __name__ == "__main__":
    main()
