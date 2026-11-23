"""Opt-in integration regression tests. All companies, events and IDs are synthetic."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import tase_registry as t
import tase_procurement_screen as screen


def sample_registry():
    today = t.now_utc()
    companies = [
        {"issuerId": 2000, "corporateId": "510000000",
         "companyName": "דוגמה תעשיות", "companyFullName": 'דוגמה תעשיות בע"מ'},
        {"issuerId": 2001, "corporateId": "510000001",
         "companyName": "דוגמה אגח", "companyFullName": 'דוגמה אגח בע"מ'},
        {"issuerId": 2002, "corporateId": "510000002",
         "companyName": "דוגמה תעשיות", "companyFullName": 'דוגמה שנייה בע"מ'},
    ]
    securities = [
        {"securityId": 1001000, "issuerId": 2000,
         "securityFullTypeCode": "0101", "securityName": "מניה"},
        {"securityId": 1001001, "issuerId": 2000,
         "securityFullTypeCode": "0501", "securityName": "אגח"},
        {"securityId": 1001002, "issuerId": 2001,
         "securityFullTypeCode": "0501", "securityName": "אגח"},
        {"securityId": 1001003, "issuerId": 2002,
         "securityFullTypeCode": "0104", "securityName": "מנית סטוק"},
    ]
    return t.build({
        "companies_he": companies,
        "companies_en": [],
        "securities": securities,
        "types": [
            {"securityFullTypeCode": "0101", "securityMainTypeDesc": "מניה"},
            {"securityFullTypeCode": "0104", "securityMainTypeDesc": "מניה"},
            {"securityFullTypeCode": "0501", "securityMainTypeDesc": 'אג"ח קונצרני'},
        ],
        "coverage": {"kind": "synthetic_test", "complete_registered_securities": False},
        "source_as_of": today.date().isoformat(),
    }, at=today.isoformat())


def example_events():
    return {
        "checked_utc": "2026-11-23T09:00:00+00:00",
        "kinds": {
            "tenders": {
                "status": "compared",
                "counts": {"new_publication": 5},
                "events": [
                    {"publication_id": "A", "event_id": "hash-1",
                     "winners": ["510000000|דוגמה תעשיות בעמ"]},
                    {"publication_id": "B", "event_id": "hash-2",
                     "winners": ["|דוגמה אגח"]},
                    {"publication_id": "C", "event_id": "hash-3",
                     "winners": ["599999999|חברה פרטית לכאורה"]},
                    {"publication_id": "D", "event_id": "hash-4",
                     "winners": ["510000000|דוגמה תעשיות",
                                 "599999999|חברה פרטית לכאורה"]},
                    {"publication_id": "E", "event_id": "hash-5",
                     "winners": ["510000000|שם שאינו תואם"]},
                    {"publication_id": "F", "event_id": "hash-6",
                     "winners": ["|דוגמה תעשיות"]},
                    {"publication_id": "G", "event_id": "hash-7",
                     "winners": ["510000001|דוגמה אגח"]},
                    {"publication_id": "H", "event_id": "hash-8",
                     "winners": []},
                ],
            },
            "exemptions": {"status": "unchanged", "events": [], "counts": {}},
        },
    }


class ProcurementTaseSidecarTests(unittest.TestCase):
    def setUp(self):
        self.registry = sample_registry()
        self.events = example_events()

    def test_exact_id_name_only_ambiguous_bond_only_and_mixed(self):
        out = screen.enrich(self.events, self.registry)
        events = out["kinds"]["tenders"]["events"]
        self.assertEqual(out["tase_enrichment"]["status"], "ready")
        self.assertTrue(events[0]["tase_screen"]["all_winners_exact_id_match"])
        self.assertEqual(events[0]["tase_screen"]["winners"][0]["type"], "שניהם")
        self.assertFalse(events[1]["tase_screen"]["all_winners_exact_id_match"])
        self.assertEqual(events[1]["tase_screen"]["winners"][0]["type"], 'אג"ח')
        self.assertTrue(events[1]["tase_screen"]["winners"][0]["requires_review"])
        self.assertEqual(events[2]["tase_screen"]["winners"][0]["status"], "לא ברשימה")
        self.assertFalse(events[3]["tase_screen"]["all_winners_exact_id_match"])
        self.assertTrue(events[4]["tase_screen"]["winners"][0]["requires_review"])
        self.assertEqual(events[5]["tase_screen"]["winners"][0]["type"], "לא חד-משמעי")
        self.assertFalse(events[6]["tase_screen"]["all_winners_exact_id_match"])
        self.assertTrue(events[6]["tase_screen"]["bond_alert"])
        self.assertFalse(events[6]["tase_screen"]["winners"][0]["auto_disqualify"])
        self.assertEqual(events[6]["tase_screen"]["winners"][0]["type"], 'אג"ח')
        self.assertEqual(events[7]["tase_screen"]["classification"], "no_winners")
        self.assertFalse(events[7]["tase_screen"]["all_winners_exact_id_match"])

    def test_preserves_every_upstream_event_and_publication_count(self):
        original = copy.deepcopy(self.events)
        enriched = screen.enrich(self.events, self.registry)
        self.assertEqual(self.events, original)
        reduced = copy.deepcopy(enriched)
        reduced.pop("tase_enrichment")
        for kind in reduced["kinds"].values():
            for event in kind["events"]:
                event.pop("tase_screen", None)
        self.assertEqual(reduced, original)
        self.assertEqual(enriched["kinds"]["tenders"]["counts"], {"new_publication": 5})
        self.assertEqual([e["event_id"] for e in enriched["kinds"]["tenders"]["events"]],
                         [e["event_id"] for e in original["kinds"]["tenders"]["events"]])

    def test_missing_corrupt_stale_registry_never_suppresses_events(self):
        for registry in ({}, {"schema_version": 999}, {
            **self.registry, "last_updated": "2024-01-01T00:00:00+00:00"
        }):
            with self.subTest(registry=registry.get("schema_version")):
                output = screen.enrich(self.events, registry)
                self.assertEqual(output["tase_enrichment"]["status"], "unavailable")
                self.assertEqual(output["tase_enrichment"]["summary"]
                                 ["events_all_winners_exact_id_match"], 0)
                for e in output["kinds"]["tenders"]["events"]:
                    self.assertFalse(e["tase_screen"]["all_winners_exact_id_match"])

    def test_prepared_matcher_same_as_regular_lookup(self):
        index = t.PreparedRegistry(self.registry)
        names = ["", "דוגמה תעשיות", 'דוגמה תעשיות בע"מ',
                 "דוגמה אגח", "שם זר", "דוגמה שנייה בעמ"]
        ids = ["", "510000000", "510000001", "510000002",
               "599999999", "123", "510000099"]
        for name in names:
            for cid in ids:
                with self.subTest(name=name, cid=cid):
                    self.assertEqual(index.decide(name=name, corporate_id=cid),
                                     t.decide(self.registry, name=name, corporate_id=cid))

    def test_no_overwrite_inputs_and_round_trip_cli(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            event_path = folder/"procurement_events.json"
            registry_path = folder/"registry.json"
            output_path = folder/"tase_enriched.json"
            original = json.dumps(self.events, ensure_ascii=False, sort_keys=True)
            event_path.write_text(original, encoding="utf-8")
            registry_path.write_text(json.dumps(self.registry, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(screen.main(["--events", str(event_path),
                                          "--registry", str(registry_path),
                                          "--output", str(output_path)]), 0)
            self.assertTrue(output_path.exists())
            self.assertEqual(event_path.read_text(encoding="utf-8"), original)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))
                             ["tase_enrichment"]["status"], "ready")
            self.assertEqual(screen.main(["--events", str(event_path),
                                          "--registry", str(registry_path),
                                          "--output", str(event_path)]), 2)

    def test_missing_registry_cli_is_nonblocking_with_all_events_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            events = root/"source.json"
            output = root/"review.json"
            events.write_text(json.dumps(self.events), encoding="utf-8")
            self.assertEqual(screen.main(["--events", str(events),
                                          "--registry", str(root/"missing.json"),
                                          "--output", str(output)]), 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["tase_enrichment"]["status"], "unavailable")
            self.assertEqual(len(result["kinds"]["tenders"]["events"]), 8)

    def test_invalid_event_input_does_not_overwrite_good_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            events = root/"bad.json"
            output = root/"existing.json"
            events.write_text(json.dumps({"kinds": {"tenders": {
                "events": ["bad event"]
            }}}), encoding="utf-8")
            output.write_text("original", encoding="utf-8")
            self.assertEqual(screen.main(["--events", str(events),
                                          "--output", str(output)]), 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "original")

    def test_large_event_batch_uses_index_not_full_scan(self):
        # 3000 distinct supplier strings against real prepared index; large
        # enough to catch quadratic revalidation while fast in CI runners.
        bulk = {"kinds": {"tenders": {"events": [
            {"event_id": str(i), "winners": [f"599{i:06d}|לא ברשימה {i}"]}
            for i in range(3000)
        ]}}}
        out = screen.enrich(bulk, self.registry)
        stats = out["tase_enrichment"]["summary"]
        self.assertEqual(stats["events_total"], 3000)
        self.assertEqual(stats["winners_not_found"], 3000)
        self.assertEqual(stats["events_all_winners_exact_id_match"], 0)


if __name__ == "__main__":
    unittest.main()
