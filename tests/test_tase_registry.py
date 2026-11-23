"""Deterministic offline tests: ALL 20 company records are synthetic, not live TASE."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import tase_registry as t

NOW = datetime(2026, 11, 23, 9, tzinfo=timezone.utc)
BOND = 'אג"ח קונצרני'


def sample():
    companies = []
    english = []
    securities = []
    for i in range(10):
        iid = 2000 + i
        cid = str(510000000 + i)
        companies.append({"issuerId": iid, "corporateId": cid,
                          "companyName": f"חברת דוגמה {i}"})
        english.append({"issuerId": iid, "corporateId": cid,
                        "companyName": f"Sample Company {i}"})
        kinds = ("B", "S") if i == 0 else (("B",) if i in (1, 2, 3) else ("S",))
        for j, kind in enumerate(kinds):
            securities.append({
                "securityId": 1200000 + i * 10 + j,
                "issuerId": iid, "corporateId": cid,
                "securityFullTypeCode": kind,
                "securityName": f"מדגם {i} {kind}",
                "_observed_on": "2026-11-20",
                "_source_endpoint": "/v1/basic-securities/trade-securities-list/2026/11/20",
            })
    return {
        "companies_he": companies, "companies_en": english,
        "types": [
            {"securityFullTypeCode": "B", "securityMainTypeDesc": "איגרות חוב",
             "securityTypeDesc": BOND},
            {"securityFullTypeCode": "S", "securityMainTypeDesc": "מניות",
             "securityTypeDesc": "מניה רגילה"},
            {"securityFullTypeCode": "G", "securityTypeDesc": 'אג"ח ממשלתי'},
            {"securityFullTypeCode": "F", "securityTypeDesc": "קרן סל"},
        ],
        "securities": securities,
        "source_as_of": "2026-11-20",
        "coverage": {"kind": "synthetic_fixture_not_official",
                     "complete_registered_securities": False},
    }


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = t.build(sample(), at=NOW.isoformat())

    def test_ten_positive_synthetic(self):
        for i in range(10):
            with self.subTest(i=i):
                r = t.decide(self.registry, corporate_id=str(510000000 + i), now=NOW)
                self.assertEqual(r["status"], "ברשימה")
                self.assertTrue(r["auto_disqualify"])
                self.assertFalse(r["requires_review"])
        self.assertEqual(t.decide(self.registry, corporate_id="510000000", now=NOW)["type"], "שניהם")
        self.assertEqual(t.decide(self.registry, corporate_id="510000001", now=NOW)["type"], 'אג"ח')

    def test_ten_negative_synthetic_are_never_private_claims(self):
        for i in range(10):
            with self.subTest(i=i):
                r = t.decide(self.registry, corporate_id=str(515000000 + i), now=NOW)
                self.assertEqual(r["status"], "לא ברשימה")
                self.assertFalse(r["auto_disqualify"])
                self.assertIn("אין בכך הוכחה", r["reason"])

    def test_name_only_exact_is_review_never_auto(self):
        r = t.decide(self.registry, name="חברת דוגמה 1", now=NOW)
        self.assertEqual(r["status"], "ברשימה")
        self.assertTrue(r["requires_review"])
        self.assertFalse(r["auto_disqualify"])

    def test_similar_name_is_not_exact(self):
        r = t.decide(self.registry, name="חברת דוגמה 1 בעמ", now=NOW)
        self.assertEqual(r["status"], "לא ברשימה")
        self.assertFalse(r["auto_disqualify"])

    def test_correct_id_but_conflicting_name_no_auto(self):
        r = t.decide(self.registry, corporate_id="510000000",
                     name="חברה אחרת", now=NOW)
        self.assertEqual(r["status"], "ברשימה")
        self.assertTrue(r["requires_review"])
        self.assertFalse(r["auto_disqualify"])

    def test_conflicting_id_and_name_no_auto(self):
        r = t.decide(self.registry, corporate_id="599999999",
                     name="חברת דוגמה 1", now=NOW)
        self.assertEqual(r["status"], "ברשימה")
        self.assertTrue(r["requires_review"])
        self.assertFalse(r["auto_disqualify"])

    def test_stale_exactly_ten_days_is_fresh(self):
        self.registry["source_as_of"] = NOW.date().isoformat()
        r = t.decide(self.registry, corporate_id="510000000",
                     now=NOW + timedelta(days=10))
        self.assertEqual(r["status"], "ברשימה")

    def test_stale_over_ten_days_fails_closed(self):
        r = t.decide(self.registry, corporate_id="510000000",
                     now=NOW + timedelta(days=11))
        self.assertEqual(r["status"], "לא ניתן לקבוע")
        self.assertFalse(r["auto_disqualify"])

    def test_source_as_of_old_despite_fresh_refresh(self):
        self.registry["source_as_of"] = "2026-10-30"
        r = t.decide(self.registry, corporate_id="510000000", now=NOW)
        self.assertEqual(r["status"], "לא ניתן לקבוע")

    def test_missing_corrupt_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "registry.json"
            self.assertEqual(t.lookup(p, corporate_id="510000000")["status"], "לא ניתן לקבוע")
            p.write_text("{not-json", encoding="utf8")
            self.assertEqual(t.lookup(p, corporate_id="510000000")["status"], "לא ניתן לקבוע")

    def test_row_count_and_bad_source_fail_closed(self):
        self.registry["row_count"] += 1
        self.assertEqual(t.decide(self.registry, corporate_id="510000000", now=NOW)["status"], "לא ניתן לקבוע")
        self.registry["row_count"] -= 1
        self.registry["rows"][0]["source_url"] = "https://evil.invalid/file.csv"
        self.assertEqual(t.decide(self.registry, corporate_id="510000000", now=NOW)["status"], "לא ניתן לקבוע")

    def test_issuer_id_conflict_discarded(self):
        raw = sample()
        raw["securities"][0]["corporateId"] = "510000001"
        reg = t.build(raw, at=NOW.isoformat())
        self.assertEqual(reg["diagnostics"]["conflicting_identifiers"], 1)
        got = t.decide(reg, corporate_id="510000000", now=NOW)
        self.assertEqual(got["type"], "מניה")

    def test_unknown_types_and_government_debt_excluded(self):
        raw = sample()
        raw["securities"].append({
            "securityId": 9000000, "issuerId": 2000, "corporateId": "510000000",
            "securityFullTypeCode": "G",
        })
        raw["securities"].append({
            "securityId": 9000001, "issuerId": 2000, "corporateId": "510000000",
            "securityFullTypeCode": "F",
        })
        reg = t.build(raw, at=NOW.isoformat())
        self.assertEqual(reg["row_count"], self.registry["row_count"])

    def test_no_redirect_and_only_official_origin(self):
        client = t.TaseClient("never-log-me", interval=0, opener=lambda *a, **k: None)
        with self.assertRaises(ValueError):
            client.get("https://other.example/bad")
        self.assertIsNone(t.NoRedirect().redirect_request(None, None, 302, "", {},
                                                           "https://untrusted.invalid"))

    def test_malformed_api_wrapper_rejected(self):
        with self.assertRaises(t.SourceError):
            t.items({"companiesList": {"result": [], "total": 0}}, "companiesList")
        with self.assertRaises(t.SourceError):
            t.items({"companiesList": {"result": [{}], "total": 5}}, "companiesList")

    def test_refresh_without_key_marks_failed_and_never_invents_data(self):
        with tempfile.TemporaryDirectory() as d, patch.dict("os.environ", {}, clear=True):
            path = Path(d) / "snapshot.json"
            self.assertEqual(t.refresh(path), 2)
            saved = t.read(path)
            self.assertEqual(saved["run_status"], "failed")
            self.assertEqual(saved["row_count"], 0)
            self.assertEqual(t.lookup(path, corporate_id="510000000")["status"], "לא ניתן לקבוע")

    def test_failed_refresh_preserves_last_known_good_data(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "snapshot.json"
            good = t.build(sample())
            t.atomic_save(path, good)
            t.mark_failed(path, "HTTP 403")
            after = t.read(path)
            self.assertEqual(after["rows"], good["rows"])
            self.assertEqual(after["run_status"], "failed")
            self.assertEqual(t.lookup(path, corporate_id="510000000")["status"], "ברשימה")

    def test_manual_requires_actual_issuer_link(self):
        raw = sample()
        for security in raw["securities"]:
            security["corporateId"] = ""
            security["issuerId"] = ""
        with self.assertRaises(t.SourceError):
            t.build(raw, at=NOW.isoformat())


if __name__ == "__main__":
    unittest.main()
