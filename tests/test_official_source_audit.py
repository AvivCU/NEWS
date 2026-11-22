import unittest
from official_source_audit import classify, SOURCES, CUES
class Tests(unittest.TestCase):
 def test_403(self): self.assertEqual(classify(403,b"",("test",)),"blocked")
 def test_challenge(self): self.assertEqual(classify(200,b"<title>Just a moment...</title>",("test",)),"blocked")
 def test_valid_content(self): self.assertEqual(classify(200,"מכרז פורסם".encode(),("מכרז",)),"content_visible")
 def test_unknown(self): self.assertEqual(classify(200,b"<title>Welcome</title>",("מכרז",)),"reachable_unverified")
 def test_false_positive_in_full_site(self): self.assertEqual(classify(200,b"<title>Tenders</title>There is advice about captcha in our FAQs. tender",("tender",)),"content_visible")
 def test_sources(self): self.assertEqual(set(SOURCES),set(CUES))
if __name__=="__main__": unittest.main()
