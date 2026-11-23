#!/usr/bin/env python3
"""Opt-in, read-only TASE enrichment for NEWS procurement event reports.

Inputs: procurement_events.json produced by daily_procurement.py and an
AUTHORIZED, LOCAL TASE registry. Outputs: a DISTINCT enriched JSON file.
No collection, publishing, filtering, Monday calls, Git writes or network.
Importing this module has no side effects on the procurement pipeline.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

from tase_registry import PreparedRegistry, read

DEFAULT_EVENTS = Path("procurement_events.json")
DEFAULT_REGISTRY = Path("data/latest/tase_registered_securities.json")
DEFAULT_OUTPUT = Path("procurement_events_tase_review.json")
MAX_EVENTS_BYTES = 90_000_000
MAX_EVENTS_PER_KIND = 10_000


def _load_events(path: Path) -> dict:
    if path.stat().st_size > MAX_EVENTS_BYTES:
        raise ValueError("Procurement events file exceeds size cap")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("kinds"), dict):
        raise ValueError("Procurement events: expected top-level kinds object")
    if not data["kinds"] or any(
        not isinstance(kind, str)
        or not isinstance(payload, dict)
        or not isinstance(payload.get("events"), list)
        or len(payload["events"]) > MAX_EVENTS_PER_KIND
        or any(not isinstance(event, dict) for event in payload["events"])
        for kind, payload in data["kinds"].items()
    ):
        raise ValueError("Procurement events: invalid event structure")
    return data


def _supplier(raw):
    """Preserve official NEWS winner encoding 'ח.פ.|שם ספק'."""
    if not isinstance(raw, str):
        raise ValueError("Procurement winner must be a string")
    corporate_id, delim, name = raw.partition("|")
    if not delim:
        return "", raw.strip()
    return corporate_id.strip(), name.strip()


def _lookup_result(result):
    """Do not echo raw TASE licensed security IDs or securities rows."""
    return {
        "status": result["status"],
        "type": result.get("type"),
        "auto_disqualify": bool(result.get("auto_disqualify", False)),
        "requires_review": bool(result.get("requires_review", False)),
        "reason": result.get("reason"),
        "match_method": result.get("match_method"),
        "equity_listed_confirmed": bool(result.get("equity_listed_confirmed")),
        "corporate_bond_confirmed": bool(result.get("corporate_bond_confirmed")),
        "scoring_signal": result.get("scoring_signal"),
    }


def enrich(data: dict, registry: dict) -> dict:
    """Never drop or reorder an event; only append explanatory TASE metadata."""
    if not isinstance(data, dict) or not isinstance(data.get("kinds"), dict):
        raise ValueError("Invalid event report")
    prepared = PreparedRegistry(registry)
    valid, invalid_reason = prepared.validation
    result = copy.deepcopy(data)
    counters = {
        "events_total": 0, "events_with_winners": 0,
        "events_all_winners_exact_id_match": 0,
        "winners_total": 0, "winners_exact_id_match": 0,
        "winners_name_only_review": 0, "winners_not_found": 0,
        "winners_unavailable": 0, "winners_other_review": 0,
        "winners_bond_only_confirmed": 0,
        "winners_equity_and_bonds_confirmed": 0,
    }
    for label, group in result["kinds"].items():
        if not isinstance(group, dict) or not isinstance(group.get("events"), list):
            raise ValueError("Invalid events in kind " + str(label))
        for event in group["events"]:
            if not isinstance(event, dict):
                raise ValueError("Invalid event item")
            winners = event.get("winners", [])
            if not isinstance(winners, list):
                raise ValueError("Winner list is malformed")
            counters["events_total"] += 1
            checked = []
            for winner in winners:
                corporate_id, company_name = _supplier(winner)
                decision = prepared.decide(name=company_name, corporate_id=corporate_id)
                code = decision["status"]
                if code == "לא ניתן לקבוע":
                    counters["winners_unavailable"] += 1
                elif decision.get("auto_disqualify"):
                    counters["winners_exact_id_match"] += 1
                elif decision.get("match_method") == "exact_name_only" or (
                    decision.get("match_method") == "ambiguous_exact_name"
                ):
                    counters["winners_name_only_review"] += 1
                elif code == "לא ברשימה" and not decision.get("requires_review"):
                    counters["winners_not_found"] += 1
                else:
                    counters["winners_other_review"] += 1
                if decision.get("corporate_bond_confirmed") and not decision.get("auto_disqualify"):
                    counters["winners_bond_only_confirmed"] += 1
                elif decision.get("corporate_bond_confirmed") and decision.get("auto_disqualify"):
                    counters["winners_equity_and_bonds_confirmed"] += 1
                checked.append({
                    "input_corporate_id": corporate_id,
                    "input_name": company_name,
                    **_lookup_result(decision),
                })
            counters["winners_total"] += len(checked)
            if checked:
                counters["events_with_winners"] += 1
            # A multi-supplier award must NOT be silently dropped if even one
            # of its suppliers has no confirmed exact-ID listing match.
            all_by_id = bool(checked) and all(
                item["auto_disqualify"] for item in checked
            )
            if all_by_id:
                counters["events_all_winners_exact_id_match"] += 1
            event["tase_screen"] = {
                "classification": (
                    "unavailable" if not valid else
                    "no_winners" if not checked else
                    "all_confirmed" if all_by_id else
                    "needs_review_or_research"
                ),
                # Advisory annotation ONLY. Never suppress upstream events.
                "all_winners_exact_id_match": all_by_id,
                "requires_followup": not all_by_id,
                "bond_alert": any(w["corporate_bond_confirmed"] for w in checked),
                "winners": checked,
            }

    result["tase_enrichment"] = {
        "status": "ready" if valid else "unavailable",
        "source_as_of": registry.get("source_as_of") if valid else None,
        "source_last_updated": registry.get("last_updated") if valid else None,
        "reason": None if valid else invalid_reason,
        "scope": "observed_TASE_shares_or_corporate_bonds_positive_only",
        "unlisted_is_not_private": True,
        "sidecar_only_upstream_events_preserved": True,
        "summary": counters,
    }
    return result


def _atomic_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tase-events-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Optional NEWS procurement TASE shadow annotator")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.output.resolve() in (args.events.resolve(), args.registry.resolve()):
        print("NEWS TASE sidecar failed: output equals input", file=sys.stderr)
        return 2
    try:
        source = _load_events(args.events)
        try:
            official = read(args.registry)
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            official = {}  # Fail closed; preserve every procurement event.
        annotated = enrich(source, official)
        _atomic_json(args.output, annotated)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        print("NEWS TASE sidecar failed: " + type(exc).__name__, file=sys.stderr)
        return 2
    # No company, contract or licensed raw security data goes to workflow logs.
    print(json.dumps({
        "status": annotated["tase_enrichment"]["status"],
        **annotated["tase_enrichment"]["summary"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
