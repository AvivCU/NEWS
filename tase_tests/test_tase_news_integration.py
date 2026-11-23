"""NEWS daily event hook contract tests; all cases are synthetic."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import tase_news_integration as stage
import tase_procurement_screen as screen
import tase_registry as tase
from test_tase_procurement_screen import sample_registry, example_events


class NewsPipelineTests(unittest.TestCase):
    def setUp(self):
        self.events = example_events()

    def test_no_new_events_skips_tase_network_completely(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dest, registry = (root/n for n in ("news.json", "out.json", "registry.json"))
            new = {"kinds": {"tenders": {"events": []}, "exemptions": {"events": []}}}
            src.write_text(json.dumps(new), encoding="utf-8")
            calls = []
            def should_not_download(_):
                calls.append(1)
                raise AssertionError("TASE contacted on zero-event NEWS batch")
            got = stage.run(src, dest, registry, download=should_not_download)
            self.assertEqual(got["stage"], "skipped_no_events")
            self.assertFalse(calls)
            self.assertFalse(dest.exists())
            self.assertFalse(registry.exists())

    def test_successful_live_shaped_registry_is_read_only_and_nonblocking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dest, registry = (root/n for n in ("news.json", "out.json", "registry.json"))
            before = json.dumps(self.events, ensure_ascii=False, indent=2)
            src.write_text(before, encoding="utf-8")
            def fake_refresh(path):
                tase.atomic_save(path, sample_registry())
                return 0
            result = stage.run(src, dest, registry, download=fake_refresh)
            self.assertEqual(result["stage"], "analyzed")
            self.assertEqual(src.read_text(encoding="utf-8"), before)
            self.assertTrue(dest.exists())
            self.assertTrue(registry.exists())
            self.assertFalse(result["published"])
            enriched = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(enriched["tase_enrichment"]["status"], "ready")
            self.assertEqual(result["screening_summary"]["events_total"], 8)
            self.assertEqual(result["screening_summary"]["events_all_winners_exact_id_match"], 2)
            self.assertEqual(len(enriched["kinds"]["tenders"]["events"]), 8)

    def test_failed_datawise_lookup_preserves_every_event(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dest, registry = (root/n for n in ("news.json", "out.json", "registry.json"))
            payload = json.dumps(self.events, ensure_ascii=False)
            src.write_text(payload, encoding="utf-8")
            def unavailable(path):
                return 2
            result = stage.run(src, dest, registry, download=unavailable)
            self.assertEqual(result["stage"], "unavailable")
            self.assertEqual(result["screening_summary"]["events_total"], 8)
            self.assertEqual(result["screening_summary"]["events_all_winners_exact_id_match"], 0)
            self.assertEqual(src.read_text(encoding="utf-8"), payload)
            enriched = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(len(enriched["kinds"]["tenders"]["events"]), 8)
            self.assertEqual(enriched["tase_enrichment"]["status"], "unavailable")

    def test_never_writes_original_events_or_registry_over_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dest, registry = (root/n for n in ("news.json", "out.json", "registry.json"))
            src.write_text(json.dumps(self.events), encoding="utf-8")
            for wrong in (src, registry):
                with self.subTest(output=wrong):
                    with self.assertRaises(ValueError):
                        stage.run(src, wrong, registry, download=lambda p: 0)
                    self.assertFalse(dest.exists())

    def test_malformed_news_report_never_calls_tase(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src, dest, registry = (root/n for n in ("news.json", "out.json", "registry.json"))
            src.write_text(json.dumps({"kinds": {"tenders": {"events": "broken"}}}), encoding="utf-8")
            hits = []
            with self.assertRaises(ValueError):
                stage.run(src, dest, registry, download=lambda p: hits.append(p))
            self.assertFalse(hits)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
