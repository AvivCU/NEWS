import unittest
from official_source_audit import classify, SOURCES, CUES

class Tests(unittest.TestCase):
    def test_challenge_200_is_blocked(self):
        self.assertEqual(classify(200, b"<title>Just a moment...</title>", ("מכרז",)), "blocked")
    def test_403_is_blocked(self):
        self.assertEqual(classify(403, b"", ("מכרז",)), "blocked")
    def test_visible(self):
        self.assertEqual(classify(200, "מכרז פורסם".encode(), ("מכרז",)), "content_visible")
    def test_generic_200_not_confirmed(self):
        self.assertEqual(classify(200, b"Welcome", ("מכרז",)), "reachable_unverified")
    def test_sources_have_cues(self):
        self.assertEqual(set(SOURCES), set(CUES))
if __name__ == "__main__":
    unittest.main()
