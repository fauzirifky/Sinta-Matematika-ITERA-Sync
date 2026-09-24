import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scrape_sinta import (  # noqa: E402
    is_publicly_limited,
    parse_collection_page,
    parse_profile,
    scrape_collection,
    fetch_soup,
    SintaSession,
    ZENROWS_ENDPOINT,
)


class FakeResponse:
    def __init__(self, html: str, url: str, content_type="text/html; charset=UTF-8"):
        self.text = html
        self.url = url
        self.headers = {"Content-Type": content_type}


class FakeSession:
    def __init__(self, html: str):
        self.html = html
        self.calls = []

    def get(self, url, params=None):
        self.calls.append({"url": url, "params": params})
        return FakeResponse(self.html, f"{url}?view={params['view']}")


class FakeApiResponse:
    status_code = 200
    text = "<html><div class='content-box'></div></html>"
    headers = {"Content-Type": "text/html; charset=UTF-8"}


class FakeHttp:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeApiResponse()

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

    def test_accepts_real_profile_with_generic_content_type(self):
        html = (ROOT / "tests" / "fixtures" / "sinta_sample.html").read_text(encoding="utf-8")
        session = mock.Mock()
        session.get.return_value = FakeResponse(html, "https://sinta.example/profile/6750161", "application/octet-stream")
        soup, _ = fetch_soup(session, "https://sinta.example/profile/6750161")
        self.assertEqual(parse_profile(soup, "6750161")["name"], "RIFKY FAUZI")

    def test_rejects_provider_json_even_with_http_200(self):
        session = mock.Mock()
        session.get.return_value = FakeResponse('{"error":"blocked"}', "https://sinta.example/profile/6750161", "application/json")
        with self.assertRaisesRegex(RuntimeError, "Content-Type: application/json; body type: JSON"):
            fetch_soup(session, "https://sinta.example/profile/6750161")

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

    def test_zenrows_builds_target_url_without_browser(self):
        with mock.patch.dict(os.environ, {"ZENROWS_API_KEY": "test-secret"}):
            session = SintaSession(45)
        fake_http = FakeHttp()
        session.http.close()
        session.http = fake_http

        response = session.get(
            "https://sinta.kemdiktisaintek.go.id/authors/profile/6750161",
            params={"view": "researches"},
        )

        self.assertEqual(len(fake_http.calls), 1)
        call = fake_http.calls[0]
        self.assertEqual(call["url"], ZENROWS_ENDPOINT)
        self.assertIn("view=researches", call["params"]["url"])
        self.assertEqual(call["params"]["premium_proxy"], "true")
        self.assertEqual(call["params"]["proxy_country"], "id")
        self.assertTrue(1 <= call["params"]["session_id"] <= 99999)
        self.assertEqual(response.url, call["params"]["url"])


if __name__ == "__main__":
    unittest.main()
