import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scrape_sinta import is_publicly_limited, parse_collection_page, parse_profile  # noqa: E402


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = (ROOT / "tests" / "fixtures" / "sinta_sample.html").read_text(encoding="utf-8")
        cls.soup = BeautifulSoup(html, "html.parser")

    def test_profile(self):
        profile = parse_profile(self.soup, "6750161")
        self.assertEqual(profile["name"], "RIFKY FAUZI")
        self.assertEqual(profile["sinta_id"], "6750161")
        self.assertEqual(profile["affiliation"], "Institut Teknologi Sumatera")
        self.assertEqual(profile["scores"]["SINTA Score Overall"], 404)

    def test_article(self):
        records = parse_collection_page(self.soup, "scopus", "https://example.test")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "A sample article")
        self.assertEqual(records[0]["classification"], "Q1 as Journal")
        self.assertEqual(records[0]["citations"], 3)
        self.assertEqual(records[0]["author_order"], "1 of 2")

    def test_public_limit(self):
        self.assertTrue(is_publicly_limited(self.soup))


if __name__ == "__main__":
    unittest.main()
