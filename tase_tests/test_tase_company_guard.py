"""TASE post-insertion company-check contract; synthetic data only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tase_company_guard as guard
import tase_registry as tase
from test_tase_procurement_screen import sample_registry


class CompanyGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Path(self.tmp.name) / "registry.json"
        tase.atomic_save(self.registry, sample_registry())

    def tearDown(self):
        self.tmp.cleanup()

    def test_equity_traded_rejected_in_all_three_destinations(self):
        for destination in sorted(guard.ALLOWED_DESTINATIONS):
            with self.subTest(destination=destination):
                result = guard.check("דוגמה תעשיות", "510000000", destination, registry=self.registry)
                self.assertEqual(result["action"], "reject_public_equity")
                self.assertTrue(result["reject"])
                self.assertTrue(result["bond_warning"])
                self.assertEqual(result["score_signal"], "strong_negative")

    def test_bond_only_is_warning_never_rejected(self):
        for destination in sorted(guard.ALLOWED_DESTINATIONS):
            with self.subTest(destination=destination):
                result = guard.check("דוגמה אגח", "510000001", destination, registry=self.registry)
                self.assertEqual(result["action"], "keep_with_bond_warning")
                self.assertFalse(result["reject"])
                self.assertTrue(result["bond_warning"])
                self.assertEqual(result["type"], 'אג"ח')
                self.assertEqual(result["score_signal"], "strong_negative")

    def test_bond_only_name_only_requires_id_review(self):
        got = guard.check("דוגמה אגח", "", "leads", registry=self.registry)
        self.assertEqual(got["action"], "manual_review")
        self.assertFalse(got["reject"])
        self.assertFalse(got["bond_warning"])
        self.assertTrue(got["requires_review"])

    def test_missing_registry_not_private_and_no_rejection(self):
        got = guard.check("דוגמה תעשיות", "510000000", "watchlist",
                          registry=Path(self.tmp.name)/"does-not-exist.json")
        self.assertEqual(got["action"], "manual_review")
        self.assertFalse(got["reject"])
        self.assertFalse(got["bond_warning"])
        self.assertEqual(got["status"], "לא ניתן לקבוע")

    def test_unknown_does_not_prove_private(self):
        got = guard.check("חברת ניסוי", "599999999", "leads", registry=self.registry)
        self.assertEqual(got["action"], "continue_existing_checks")
        self.assertFalse(got["reject"])
        self.assertFalse(got["bond_warning"])

    def test_invalid_target_rejected(self):
        with self.assertRaises(ValueError):
            guard.check("דוגמה אגח", "510000001", "unapproved_target",
                        registry=self.registry)

    def test_name_id_mismatch_never_auto_rejects(self):
        got = guard.check("שם לא קשור", "510000000", "owned_company_watchlist",
                          registry=self.registry)
        self.assertEqual(got["action"], "manual_review")
        self.assertFalse(got["reject"])
        self.assertFalse(got["bond_warning"])
        self.assertTrue(got["requires_review"])


if __name__ == "__main__":
    unittest.main()
