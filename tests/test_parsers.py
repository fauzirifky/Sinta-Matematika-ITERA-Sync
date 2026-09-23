import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scrape_sinta import (  # noqa: E402
    is_publicly_limited,
    parse_collection_page,
    parse_profile,
    scrape_collection,
    BROWSER_HEADERS,
    SINTA_ORIGIN,
    SintaSession,
)


class FakeResponse:
    def __init__(self, html: str, url: str):
        self.text = html
        self.url = url
        self.headers = {"Content-Type": "text/html; charset=UTF-8"}


class FakeSession:
    def __init__(self, html: str):
        self.html = html
        self.calls = []

    def get(self, url, params=None):
        self.calls.append({"url": url, "params": params})
        return FakeResponse(self.html, f"{url}?view={params['view']}")


class FakeHttpResponse:
    def __init__(self, url):
        self.status_code = 200
        self.text = "<html><div class='content-box'></div></html>"
        self.headers = {"Content-Type": "text/html; charset=UTF-8"}
        self.url = url

    def raise_for_status(self):
        pass


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.cookies = []
        self.headers = {}

    def get(self, url, params=None, headers=None, timeout=None, allow_redirects=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
                "allow_redirects": allow_redirects,
            }
        )
        suffix = "?view=" + params["view"] if params else ""
        return FakeHttpResponse(url + suffix)

    def close(self):
        pass


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

    def test_collection_fetches_only_initial_public_page(self):
        html = (ROOT / "tests" / "fixtures" / "sinta_sample.html").read_text(encoding="utf-8")
        session = FakeSession(html)
        result = scrape_collection(
            session,
            "https://sinta.example/authors/profile/6750161",
            "scopus",
            "scopus",
        )

        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["params"], {"view": "scopus"})
        self.assertEqual(result["scope"], "public_first_page_only")
        self.assertEqual(result["pages_collected"], 1)

    def test_public_session_bootstrap_and_referer(self):
        session = SintaSession(45)
        fake_http = FakeHttp()
        session.http.close()
        session.http = fake_http

        response = session.get(
            "https://sinta.kemdiktisaintek.go.id/authors/profile/6750161",
            params={"view": "researches"},
        )

        self.assertEqual(len(fake_http.calls), 2)
        bootstrap, profile = fake_http.calls
        self.assertEqual(bootstrap["url"], f"{SINTA_ORIGIN}/")
        self.assertEqual(bootstrap["headers"]["Sec-Fetch-Site"], "none")
        self.assertEqual(profile["params"], {"view": "researches"})
        self.assertEqual(profile["headers"]["Referer"], f"{SINTA_ORIGIN}/")
        self.assertEqual(profile["headers"]["Sec-Fetch-Site"], "same-origin")
        self.assertIn("view=researches", response.url)

    def test_browser_headers_are_present(self):
        self.assertIn("Mozilla/5.0", BROWSER_HEADERS["User-Agent"])
        self.assertIn("text/html", BROWSER_HEADERS["Accept"])


if __name__ == "__main__":
    unittest.main()
