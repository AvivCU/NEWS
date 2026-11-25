import re
import unittest
from body_evidence import nearby_event


class BodyEvidence(unittest.TestCase):
    def test_local_event(self):
        self.assertTrue(nearby_event("discussion alpha widgets signed agreement", re.compile("alpha widgets"), lambda s: "signed" in s.split()))

    def test_distant_event(self):
        text = "alpha widgets " + "neutral " * 20 + "signed agreement"
        self.assertFalse(nearby_event(text, re.compile("alpha widgets"), lambda s: "signed" in s.split()))

    def test_multiple_mentions(self):
        text = "alpha widgets " + "neutral " * 20 + "alpha widgets signed agreement"
        self.assertTrue(nearby_event(text, re.compile("alpha widgets"), lambda s: "signed" in s.split()))

    def test_no_entity(self):
        self.assertFalse(nearby_event("signed agreement", re.compile("alpha widgets"), lambda s: True))


if __name__ == "__main__":
    unittest.main()
