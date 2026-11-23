#!/usr/bin/env python3
"""NEWS optional, fail-open TASE shadow-stage: run AFTER daily_procurement.

No changes to the source report/snapshots, no Monday, no network except the
official TASE allowlisted GETs through tase_registry.TaseClient. All enriched
company/event details remain ephemeral and must NEVER be uploaded to public
Actions artifacts or published in repository commits.

Note: this stage adds a NEWS-specific classification, not a replacement for
the private Rosario Feeds news agent. Exclusion is advisory, not destructive.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import tase_procurement_screen as screen
import tase_registry as tase


def summary(events: dict) -> dict:
    """Avoid TASE calls on unchanged feeds, while handling malformed input."""
    if not isinstance(events, dict) or not isinstance(events.get("kinds"), dict):
        raise ValueError("Bad NEWS event report")
    counts = {}
    for kind, data in events["kinds"].items():
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise ValueError("Malformed NEWS event list")
        counts[kind] = len(data["events"])
    return counts


def run(events: Path, output: Path, registry: Path, *,
        download=tase.refresh) -> dict:
    if output.resolve() in (events.resolve(), registry.resolve()):
        raise ValueError("Shadow output must not overwrite inputs")
    original = screen._load_events(events)
    counts = summary(original)
    if not any(counts.values()):
        # No official TASE request and no private by-company outputs produced.
        return {"stage": "skipped_no_events", "input_events_by_kind": counts,
                "source_events_unchanged": True, "published": False}
    result = download(registry)
    if result != 0:
        # A source failure is NO reason to drop or suppress government events.
        # Use fail-closed unavailable annotations in a separate temp output.
        source = tase.read(registry) if registry.exists() else {}
        enriched = screen.enrich(original, source)
        status = "unavailable"
    else:
        enriched = screen.enrich(original, tase.read(registry))
        status = enriched["tase_enrichment"]["status"]
    screen._atomic_json(output, enriched)
    return {
        "stage": "analyzed" if status == "ready" else "unavailable",
        "input_events_by_kind": counts,
        "source_events_unchanged": True,
        "published": False,
        "screening_summary": enriched["tase_enrichment"]["summary"],
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--events", type=Path, default=screen.DEFAULT_EVENTS)
    p.add_argument("--registry", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        record = run(args.events, args.output, args.registry)
        print(json.dumps(record, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # Redact details, e.g. an invalid JSON message may contain private data.
        print("TASE shadow unavailable: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
