#!/usr/bin/env python3
"""NEWS historical public procurement baseline ↔ live TASE screening QA.

Source: committed REAL government procurement snapshot, not fake sample data.
This is a retrospective historical cross-section, NOT new tender alerts.
Output: aggregate metrics only; never print supplier names, corporate IDs,
licensed TASE records, or event documents. No uploads or Git modifications.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import json
from pathlib import Path
import tempfile
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tase_registry
import tase_procurement_screen as screen
import tase_news_integration as news_stage


def sample_from_snapshot(path: Path, *, max_events=2500) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as file:
        snapshot = json.load(file)
    if snapshot.get("schema") != 2 or snapshot.get("kind") not in ("tenders", "exemptions"):
        raise ValueError("Expected authentic schema v2 procurement snapshot")
    items = snapshot.get("items")
    if not isinstance(items, dict) or len(items) < 1000:
        raise ValueError("Procurement snapshot unexpectedly empty")
    selected = []
    used = set()
    # Spread alphabetically sorted publication IDs; no sampling off system time.
    # At most 2500 genuine historical publications containing awarded suppliers.
    for pub_id, entry in sorted(items.items()):
        winners = entry.get("winners", [])
        if not isinstance(winners, list) or not winners:
            continue
        raw = [w for w in winners[:15] if isinstance(w, str) and "|" in w]
        if not raw:
            continue
        key = tuple(raw)
        if key in used:
            continue
        used.add(key)
        selected.append({
            "publication_id": pub_id, "event_id": "historical_sample_" + str(len(selected)),
            "winners": raw, "change_types": ["historical_sample_only"],
            "title": entry.get("title", ""), "agency": entry.get("agency", ""),
            "published": entry.get("published", ""),
        })
        if len(selected) >= max_events:
            break
    if len(selected) < 50:
        raise ValueError("Not enough real known suppliers in procurement snapshot")
    return {
        "checked_utc": "2026-11-23T00:00:00+00:00",
        "sample_type": "historical_real_procurement_baseline_not_recent_events",
        "kinds": {"tenders": {"status": "historical_sample",
                              "counts": {"baseline_sample": len(selected)},
                              "events": selected}},
    }


def audit(snapshot: Path, registry: Path, max_events=2500) -> dict:
    source = sample_from_snapshot(snapshot, max_events=max_events)
    original = copy.deepcopy(source)
    clock = perf_counter()
    enriched = screen.enrich(source, tase_registry.read(registry))
    elapsed = round(perf_counter() - clock, 3)
    if enriched["tase_enrichment"]["status"] != "ready":
        raise ValueError("TASE source unusable in real government baseline test")
    assert source == original, "Input government records mutated"
    rows = enriched["kinds"]["tenders"]["events"]
    if len(rows) != len(original["kinds"]["tenders"]["events"]):
        raise ValueError("Government procurement events lost")
    assert all(x["event_id"] == y["event_id"] and x["winners"] == y["winners"]
               for x, y in zip(rows, original["kinds"]["tenders"]["events"]))
    result = enriched["tase_enrichment"]["summary"]
    if result["events_total"] != len(rows):
        raise ValueError("Incorrect count of government events")
    if result["events_all_winners_exact_id_match"] > result["events_with_winners"]:
        raise ValueError("Wrong positive count")
    for event in rows:
        classified = event["tase_screen"]
        if classified["all_winners_exact_id_match"]:
            if any(w["requires_review"] or not w["auto_disqualify"]
                   or w["match_method"] != "exact_corporate_id"
                   for w in classified["winners"]):
                raise ValueError("False automatic rejection in historical data")
        for winner in classified["winners"]:
            if winner["auto_disqualify"] and winner["match_method"] != "exact_corporate_id":
                raise ValueError("Name-only false disqualification")
    # Exercise the EXACT daily NEWS hook end-to-end with real historical
    # supplier records, an authenticated TASE snapshot and ephemeral files.
    # Simulate the already-completed TASE refresh using the fetched snapshot;
    # do not waste another 28 API calls for the same data.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src, dst, intermediate = (root/x for x in ("news_events.json", "screened_events.json", "tase.json"))
        src.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        before = src.read_bytes()
        def inject_live_snapshot(target):
            tase_registry.atomic_save(target, tase_registry.read(registry))
            return 0
        hook_result = news_stage.run(src, dst, intermediate, download=inject_live_snapshot)
        if hook_result["stage"] != "analyzed" or not dst.exists():
            raise ValueError("NEWS daily hook failed against real supplier sample")
        if src.read_bytes() != before:
            raise ValueError("NEWS daily hook modified real input records")
        saved = json.loads(dst.read_text(encoding="utf-8"))
        if saved["tase_enrichment"]["summary"] != result:
            raise ValueError("NEWS hook and direct TASE classifier diverged")
        original_ids = [e["event_id"] for e in original["kinds"]["tenders"]["events"]]
        screened_ids = [e["event_id"] for e in saved["kinds"]["tenders"]["events"]]
        if screened_ids != original_ids:
            raise ValueError("NEWS daily hook changed order or identifiers")

    # Report only aggregate metrics; never reveal underlying companies.
    return {
        "status": "PASS", "sample_origin": "real_news_" + snapshot.stem.split(".")[0] + "_baseline_2026_11",
        "historical_not_new_leads": True,
        "source_events_unchanged": True, "no_auto_exclusion_applied": True,
        "real_supplier_records_passed_through_daily_hook": True,
        "duration_seconds": elapsed, **result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=Path("state/procurement_snapshots/exemptions.json.gz"))
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()
    if not 50 <= args.limit <= 5000:
        parser.error("Limit must be 50..5000")
    print(json.dumps(audit(args.snapshot, args.registry, args.limit), ensure_ascii=False))


if __name__ == "__main__":
    main()
