#!/usr/bin/env python3
"""Scrape public SINTA author pages into stable, versioned JSON files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_BASE_URL = "https://sinta.kemdiktisaintek.go.id/authors/profile"
ZENROWS_ENDPOINT = "https://api.zenrows.com/v1/"
SCHEMA_VERSION = 2

COLLECTIONS = {
    "scopus": "scopus",
    "garuda": "garuda",
    "google_scholar": "googlescholar",
    "rama": "rama",
    "researches": "researches",
    "community_services": "services",
    "iprs": "iprs",
    "books": "books",
}


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def integer_from_text(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"-?\d[\d.,]*", value)
    if not match:
        return None
    digits = re.sub(r"[^\d-]", "", match.group(0))
    try:
        return int(digits)
    except ValueError:
        return None


def value_after_label(text: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}\s*:\s*(.+?)(?=(?:\s{{2,}}|$))", text, re.I)
    return clean_text(match.group(1)) if match else None


def labeled_value_from_nodes(item: Tag, label: str) -> str | None:
    """Read a labelled value from one SINTA element without swallowing neighbours."""
    prefix = re.compile(rf"^{re.escape(label)}\s*:\s*", re.I)
    # Labels on SINTA records are individual anchors/spans. Avoid container divs,
    # whose text also contains the neighbouring scheme or holder.
    for node in item.select("a, span"):
        text = clean_text(node.get_text(" ", strip=True))
        if text and prefix.match(text):
            value = prefix.sub("", text, count=1)
            return clean_text(value)
    return None


def stable_id(collection: str, title: str | None, url: str | None) -> str:
    material = f"{collection}|{title or ''}|{url or ''}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:20]


def absolute_url(base_url: str, href: str | None) -> str | None:
    if not href or href == "#!":
        return None
    return urljoin(base_url, href)


class SintaSession:
    """Fetch public SINTA HTML through the lightweight ZenRows API."""

    def __init__(self, timeout: float):
        self.timeout = max(timeout, 30.0)
        self.api_key = clean_text(os.environ.get("ZENROWS_API_KEY"))
        if not self.api_key:
            raise RuntimeError(
                "ZENROWS_API_KEY is missing. Add it at GitHub repository Settings > "
                "Secrets and variables > Actions."
            )

        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        self.http = requests.Session()
        self.http.mount("https://", HTTPAdapter(max_retries=retry))
        self._announced = False
        self.session_id = None
        self.known_credits = 0
        self.unknown_cost_requests = 0

    def get(self, url: str, params: dict[str, Any] | None = None):
        prepared = requests.Request("GET", url, params=params).prepare()
        target_url = prepared.url
        if not target_url:
            raise RuntimeError("Could not build the SINTA target URL.")

        # Session IDs must be in ZenRows' documented range 1..99999. Using the
        # same ID for this run keeps the exit IP stable across author tabs.
        if self.session_id is None:
            self.session_id = int.from_bytes(os.urandom(4), "big") % 99999 + 1
        try:
            response = self.http.get(
                ZENROWS_ENDPOINT,
                params={
                    "apikey": self.api_key,
                    "url": target_url,
                    # Adaptive mode starts with the cheapest viable transport
                    # and escalates only when SINTA rejects it. Do not specify
                    # proxy_country: doing so can force a Premium Proxy.
                    "mode": "auto",
                    "session_id": self.session_id,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            # The full request URL contains the API key; never log the exception.
            raise RuntimeError(
                "ZenRows request failed at network level. Check the service status "
                "and GitHub Actions connectivity."
            ) from None
        if response.status_code >= 400:
            raise RuntimeError(
                f"ZenRows API returned HTTP {response.status_code}. "
                "Check the API key, remaining credits, and provider dashboard."
            )

        if not self._announced:
            print("  Fetch transport: ZenRows Adaptive Stealth Mode", flush=True)
            self._announced = True

        request_cost = clean_text(response.headers.get("X-Request-Cost"))
        if request_cost and request_cost.isdigit():
            self.known_credits += int(request_cost)
            print(f"    ZenRows cost: {request_cost} credit(s) — {target_url}", flush=True)
        else:
            self.unknown_cost_requests += 1
            print(f"    ZenRows cost: unknown — {target_url}", flush=True)

        return FetchedResponse(
            text=response.text,
            url=target_url,
            headers={"Content-Type": response.headers.get("Content-Type", "unknown")},
        )

    def close(self) -> None:
        self.http.close()


class FetchedResponse:
    def __init__(self, text: str, url: str, headers: dict[str, str]):
        self.text = text
        self.url = url
        self.headers = headers


def make_session(timeout: float) -> SintaSession:
    return SintaSession(timeout)


def fetch_soup(
    session: SintaSession,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> tuple[BeautifulSoup, str]:
    response = session.get(url, params=params)
    soup = BeautifulSoup(response.text, "html.parser")
    # ZenRows may forward HTML with a generic Content-Type. Validate the actual
    # SINTA profile structure instead of trusting that header alone.
    profile_id = soup.select_one(".meta-profile")
    if not (soup.select_one(".content-box h3 a") and profile_id and
            re.search(r"SINTA\s*ID\s*:\s*\d+", profile_id.get_text(" ", strip=True), re.I)):
        content_type = response.headers.get("Content-Type", "unknown")
        # Print only a safe media type, never the response body or request URL
        # containing the ZenRows key.
        media_type = content_type.split(";", 1)[0].strip().lower()
        if not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", media_type):
            media_type = "unknown"
        body_type = "JSON" if response.text.lstrip().startswith(("{", "[")) else "HTML or text" if soup.find("html") else "other"
        raise RuntimeError(
            f"ZenRows returned a response without a valid SINTA profile "
            f"(Content-Type: {media_type}; body type: {body_type}) at {response.url}. "
            "Check the ZenRows request log for the upstream response."
        )
    return soup, str(response.url)


def parse_profile(soup: BeautifulSoup, configured_id: str) -> dict[str, Any]:
    name_node = soup.select_one(".content-box h3 a")
    meta = soup.select_one(".meta-profile")
    avatar = soup.select_one(".content-box img[alt='avatar']")

    affiliation = None
    affiliation_url = None
    department = None
    department_url = None
    discovered_id = configured_id

    if meta:
        for link in meta.select("a"):
            href = link.get("href")
            text = clean_text(link.get_text(" ", strip=True))
            if href and "/affiliations/profile/" in href:
                affiliation = text
                affiliation_url = href
            elif href and "/departments/profile/" in href:
                department = text
                department_url = href
            elif text and "SINTA ID" in text.upper():
                match = re.search(r"SINTA\s*ID\s*:\s*(\d+)", text, re.I)
                if match:
                    discovered_id = match.group(1)

    scores: dict[str, int | str | None] = {}
    for block in soup.select(".stat-profile .col-4"):
        label = clean_text(block.select_one(".pr-txt").get_text(" ", strip=True)) if block.select_one(".pr-txt") else None
        number = clean_text(block.select_one(".pr-num").get_text(" ", strip=True)) if block.select_one(".pr-num") else None
        if label:
            scores[label] = integer_from_text(number) if integer_from_text(number) is not None else number

    subjects = [
        clean_text(node.get_text(" ", strip=True))
        for node in soup.select(".profile-subject .subject-list a")
    ]

    return {
        "name": clean_text(name_node.get_text(" ", strip=True)) if name_node else None,
        "sinta_id": discovered_id,
        "affiliation": affiliation,
        "affiliation_url": affiliation_url,
        "department": department,
        "department_url": department_url,
        "avatar_url": avatar.get("src") if isinstance(avatar, Tag) else None,
        "subjects": [subject for subject in subjects if subject],
        "scores": scores,
    }


def parse_pagination(soup: BeautifulSoup) -> tuple[int, int | None]:
    pagination = soup.select_one(".pagination-text")
    if not pagination:
        return 1, None
    text = clean_text(pagination.get_text(" ", strip=True)) or ""
    page_match = re.search(r"Page\s+\d+\s+of\s+(\d+)", text, re.I)
    total_match = re.search(r"Total\s+Records\s+(\d+)", text, re.I)
    pages = int(page_match.group(1)) if page_match else 1
    total = int(total_match.group(1)) if total_match else None
    return max(pages, 1), total


def parse_common_item(item: Tag, collection: str, page_url: str) -> dict[str, Any]:
    title_link = item.select_one(".ar-title a")
    title = clean_text(title_link.get_text(" ", strip=True)) if title_link else None
    item_url = absolute_url(page_url, title_link.get("href")) if title_link else None
    raw_text = clean_text(item.get_text(" ", strip=True))
    year_node = item.select_one(".ar-year")
    year = integer_from_text(year_node.get_text(" ", strip=True)) if year_node else None

    record: dict[str, Any] = {
        "id": stable_id(collection, title, item_url),
        "title": title,
        "url": item_url,
        "year": year,
        "source_page": page_url,
    }

    if collection in {"scopus", "garuda", "google_scholar", "rama"}:
        publication = item.select_one(".ar-pub")
        quartile = item.select_one(".ar-quartile")
        cited = item.select_one(".ar-cited")
        record.update(
            {
                "classification": clean_text(quartile.get_text(" ", strip=True)) if quartile else None,
                "publication": clean_text(publication.get_text(" ", strip=True)) if publication else None,
                "publication_url": absolute_url(page_url, publication.get("href")) if publication else None,
                "author_order": labeled_value_from_nodes(item, "Author Order"),
                "creator": labeled_value_from_nodes(item, "Creator"),
                "citations": integer_from_text(cited.get_text(" ", strip=True)) if cited else None,
            }
        )
    elif collection in {"researches", "community_services"}:
        scheme = item.select_one(".ar-pub")
        personnel = []
        for link in item.select("a[href*='/authors/profile/']"):
            person_name = clean_text(link.get_text(" ", strip=True))
            if person_name:
                personnel.append(
                    {
                        "name": person_name.rstrip(";"),
                        "url": absolute_url(page_url, link.get("href")),
                    }
                )
        funding_match = re.search(r"Rp\.?\s*([\d.]+)", raw_text or "", re.I)
        source_match = re.search(r"\b(BIMA|INTERNAL)\s+SOURCE\b", raw_text or "", re.I)
        status_match = re.search(r"\b(Approved|Rejected|Proposed|Draft)\b", raw_text or "", re.I)
        record.update(
            {
                "leader": labeled_value_from_nodes(item, "Leader"),
                "scheme": clean_text(scheme.get_text(" ", strip=True)) if scheme else None,
                "personnel": personnel,
                "funding_idr": integer_from_text(funding_match.group(1)) if funding_match else None,
                "status": status_match.group(1) if status_match else None,
                "funding_source_type": source_match.group(1).upper() if source_match else None,
            }
        )
    elif collection == "iprs":
        holder = item.select_one(".ar-pub")
        cited_nodes = [clean_text(node.get_text(" ", strip=True)) for node in item.select(".ar-cited")]
        application_number = None
        status = None
        for text in cited_nodes:
            if not text:
                continue
            if text.lower().startswith("nomor permohonan"):
                application_number = value_after_label(text, "Nomor Permohonan")
            elif text.lower().startswith("status"):
                status = value_after_label(text, "Status")
        ipr_type = item.select_one(".ar-quartile")
        record.update(
            {
                "inventors": labeled_value_from_nodes(item, "Inventor"),
                "holder": clean_text(holder.get_text(" ", strip=True)) if holder else None,
                "application_number": application_number,
                "status": status,
                "ipr_type": clean_text(ipr_type.get_text(" ", strip=True)) if ipr_type else None,
            }
        )
    elif collection == "books":
        publisher = item.select_one(".ar-pub")
        category_match = re.search(r"Category\s*:\s*(.+?)(?=\s{2,}|$)", raw_text or "", re.I)
        isbn_match = re.search(r"ISBN\s*:\s*([\dXx-]+)", raw_text or "", re.I)
        meta_blocks = item.select(".ar-meta")
        authors = None
        if len(meta_blocks) >= 2:
            author_block = meta_blocks[1]
            author_text = clean_text(author_block.get_text(" ", strip=True)) or ""
            publisher_text = clean_text(publisher.get_text(" ", strip=True)) if publisher else None
            if publisher_text and author_text.endswith(publisher_text):
                author_text = clean_text(author_text[: -len(publisher_text)]) or ""
            authors = author_text or None
        record.update(
            {
                "category": labeled_value_from_nodes(item, "Category")
                or (clean_text(category_match.group(1)) if category_match else None),
                "authors": authors,
                "publisher": clean_text(publisher.get_text(" ", strip=True)) if publisher else None,
                "isbn": isbn_match.group(1) if isbn_match else None,
            }
        )

    return record


def parse_collection_page(
    soup: BeautifulSoup,
    collection: str,
    page_url: str,
) -> list[dict[str, Any]]:
    return [
        parse_common_item(item, collection, page_url)
        for item in soup.select(".profile-article .ar-list-item")
    ]


def is_publicly_limited(soup: BeautifulSoup) -> bool:
    return any(
        "view more" in (clean_text(link.get_text(" ", strip=True)) or "").lower()
        and "/logins" in (link.get("href") or "")
        for link in soup.select("a")
    )


def scrape_collection(
    session: SintaSession,
    profile_url: str,
    collection: str,
    view: str,
) -> dict[str, Any]:
    # Intentionally request only the initial public page. We never follow SINTA's
    # pagination or its login-only "View more" link.
    soup, page_url = fetch_soup(session, profile_url, params={"view": view})
    return collection_result_from_soup(soup, collection, view, page_url)


def collection_result_from_soup(
    soup: BeautifulSoup,
    collection: str,
    view: str,
    page_url: str,
) -> dict[str, Any]:
    _available_pages, reported_total = parse_pagination(soup)
    records = parse_collection_page(soup, collection, page_url)
    limited = is_publicly_limited(soup)

    unique_records = {record["id"]: record for record in records}
    ordered = list(unique_records.values())
    return {
        "view": view,
        "scope": "public_first_page_only",
        "pages_collected": 1,
        "reported_total": reported_total,
        "records_collected": len(ordered),
        "public_access_limited": limited,
        "records": ordered,
    }


def parse_metrics(soup: BeautifulSoup, page_url: str) -> dict[str, Any]:
    summary: dict[str, dict[str, int | str | None]] = {}
    stat_table = soup.select_one("table.stat-table")
    if stat_table:
        headers = [clean_text(th.get_text(" ", strip=True)) for th in stat_table.select("thead th")]
        sources = [header for header in headers[1:] if header]
        for row in stat_table.select("tbody tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.select("th, td")]
            if not cells or not cells[0]:
                continue
            values: dict[str, int | str | None] = {}
            for source, value in zip(sources, cells[1:]):
                parsed = integer_from_text(value)
                values[source] = parsed if parsed is not None else value
            summary[cells[0]] = values

    score_rows: list[dict[str, Any]] = []
    metrics_table = next(
        (table for table in soup.select("table.table") if not "stat-table" in (table.get("class") or [])),
        None,
    )
    if metrics_table:
        for row in metrics_table.select("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.select(":scope > th, :scope > td")]
            if len(cells) < 13 or not cells[1] or not re.fullmatch(r"[A-Z]+\d+", cells[1]):
                continue
            score_rows.append(
                {
                    "code": cells[1],
                    "name": cells[2],
                    "sinta_weight": integer_from_text(cells[3]),
                    "sinta_overall_value": integer_from_text(cells[4]),
                    "sinta_overall_total": integer_from_text(cells[5]),
                    "sinta_3yr_value": integer_from_text(cells[6]),
                    "sinta_3yr_total": integer_from_text(cells[7]),
                    "affiliation_weight": integer_from_text(cells[8]),
                    "affiliation_overall_value": integer_from_text(cells[9]),
                    "affiliation_overall_total": integer_from_text(cells[10]),
                    "affiliation_3yr_value": integer_from_text(cells[11]),
                    "affiliation_3yr_total": integer_from_text(cells[12]),
                }
            )

    return {
        "source_page": page_url,
        "summary": summary,
        "score_rows": score_rows,
    }


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    temporary.replace(path)


def validate_author(author: dict[str, Any]) -> dict[str, Any]:
    name = clean_text(str(author.get("name", "")))
    sinta_id = clean_text(str(author.get("sinta_id", "")))
    if not name:
        raise ValueError("Each author must have a non-empty 'name'.")
    if not sinta_id or not sinta_id.isdigit():
        raise ValueError(f"Author {name!r} must have a numeric 'sinta_id'.")
    profile_url = clean_text(str(author.get("profile_url", ""))) or f"{DEFAULT_BASE_URL}/{sinta_id}"
    if not profile_url.startswith("https://sinta.kemdiktisaintek.go.id/authors/profile/"):
        raise ValueError(f"Author {name!r} has an unsupported SINTA profile URL.")
    return {
        "name": name,
        "sinta_id": sinta_id,
        "profile_url": profile_url,
        "enabled": bool(author.get("enabled", True)),
    }


def scrape_author(
    session: SintaSession,
    author: dict[str, Any],
    output_dir: Path,
    delay: float,
    view: str,
) -> tuple[dict[str, Any], bool]:
    author_path = output_dir / f"{author['sinta_id']}.json"
    previous = load_json(author_path, {})
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if view == "scopus":
        profile_soup, profile_page_url = fetch_soup(session, author["profile_url"])
    else:
        profile_soup, profile_page_url = fetch_soup(
            session, author["profile_url"], params={"view": "matrics" if view == "metrics" else COLLECTIONS[view]}
        )
    profile = parse_profile(profile_soup, author["sinta_id"])
    if profile.get("sinta_id") != author["sinta_id"] or not profile.get("name"):
        raise RuntimeError(
            f"Configured SINTA ID {author['sinta_id']} does not match page ID {profile.get('sinta_id')}"
        )
    collections: dict[str, Any] = previous.get("collections", {}).copy()
    statuses: dict[str, Any] = previous.get("collection_status", {}).copy()
    metrics = previous.get("metrics", {})
    if view == "metrics":
        metrics = parse_metrics(profile_soup, profile_page_url)
    else:
        fresh = collection_result_from_soup(profile_soup, view, COLLECTIONS[view], profile_page_url)
        old = collections.get(view, {}).get("records", [])
        # The public first page is only a window. Keep older known records,
        # including the user's initial snapshot, while refreshing visible items.
        merged = {}
        for item in old + fresh["records"]:
            key = (item.get("url") or item.get("title") or item.get("id"))
            merged[key] = item
        fresh["records"] = list(merged.values())
        fresh["records_collected"] = len(merged)
        fresh["scope"] = "public_first_page_plus_preserved_records"
        collections[view] = fresh
    statuses[view] = {"status": "ok", "checked_at": now}
    # Scores are displayed on every public profile tab.
    if not profile.get("subjects") and previous.get("profile", {}).get("subjects"):
        profile["subjects"] = previous["profile"]["subjects"]
    if not profile.get("scores") and previous.get("profile", {}).get("scores"):
        profile["scores"] = previous["profile"]["scores"]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "source": {
            "service": "SINTA - Science and Technology Index",
            "profile_url": profile_page_url,
            "access": "first public page only; no login and no View more",
        },
        "configured_author": author,
        "profile": profile,
        "collections": collections,
        "metrics": metrics,
        "collection_status": statuses,
    }
    if "manual_baseline" in previous:
        payload["manual_baseline"] = previous["manual_baseline"]
    write_json(author_path, payload)
    return payload, False


def build_manifest(output_dir: Path, authors_config: list[dict[str, Any]]) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    authors = []
    for configured in authors_config:
        payload = load_json(output_dir / f"{configured['sinta_id']}.json", None)
        if not isinstance(payload, dict):
            continue
        profile = payload["profile"]
        counts = {
            key: value.get("records_collected", 0)
            for key, value in payload["collections"].items()
        }
        authors.append(
            {
                "name": profile.get("name") or payload["configured_author"]["name"],
                "sinta_id": profile.get("sinta_id"),
                "file": f"{profile.get('sinta_id')}.json",
                "status": "ok" if payload.get("generated_at") else "manual_baseline",
                "counts": counts,
            }
        )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "authors_count": len(authors),
        "authors": authors,
    }
    write_json(output_dir / "index.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/authors.json"))
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--author-id", help="Only scrape one configured SINTA ID")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API requests")
    parser.add_argument("--timeout", type=float, default=45.0, help="HTTP timeout in seconds")
    parser.add_argument("--check-config", action="store_true", help="Validate config and exit")
    parser.add_argument("--view", choices=[*COLLECTIONS, "metrics"], help="Request this one tab per author")
    parser.add_argument("--all-views", action="store_true", help="Request every tab (9 paid requests per author)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_authors = load_json(args.config, None)
    if not isinstance(raw_authors, list):
        raise ValueError(f"{args.config} must contain a JSON array.")

    configured_authors = [validate_author(author) for author in raw_authors]
    authors = configured_authors
    authors = [author for author in authors if author["enabled"]]
    if args.author_id:
        authors = [author for author in authors if author["sinta_id"] == args.author_id]
    if not authors:
        raise ValueError("No enabled authors matched the requested configuration.")

    if args.check_config:
        print(f"Configuration is valid: {len(authors)} enabled author(s).")
        return 0

    if args.delay < 0:
        raise ValueError("--delay cannot be negative.")
    if args.view and args.all_views:
        raise ValueError("Choose either --view or --all-views.")

    # Complete mode is the default. --view exists only for a targeted test or
    # manual repair of one category.
    tabs = [*COLLECTIONS, "metrics"]
    views = [args.view] if args.view else tabs
    print(f"Public tab(s) for this run: {', '.join(views)}. Requests per author: {len(views)}.", flush=True)

    results: list[tuple[dict[str, Any], bool]] = []
    fatal_errors: list[str] = []
    session = make_session(args.timeout)
    try:
        for author in authors:
            print(f"Scraping {author['name']} (SINTA ID {author['sinta_id']})...", flush=True)
            try:
                for index, chosen in enumerate(views):
                    if index:
                        time.sleep(args.delay)
                    payload, had_errors = scrape_author(session, author, args.output, args.delay, chosen)
                results.append((payload, had_errors))
                print(
                    f"  saved {args.output / (author['sinta_id'] + '.json')}"
                    + (" with partial/stale sections" if had_errors else ""),
                    flush=True,
                )
            except Exception as exc:
                fatal_errors.append(f"{author['name']} ({author['sinta_id']}): {exc}")
                print(f"  ERROR: {exc}", file=sys.stderr, flush=True)
                # Do not spend another author's API credits after a provider failure.
                break
            if author != authors[-1]:
                time.sleep(args.delay)
    finally:
        print(
            f"ZenRows credits reported by responses: {session.known_credits}; "
            f"unknown-cost requests: {session.unknown_cost_requests}.",
            flush=True,
        )
        session.close()

    if results:
        manifest = build_manifest(args.output, configured_authors)
        print(f"Saved manifest for {manifest['authors_count']} author(s).", flush=True)

    if fatal_errors:
        print("Fatal author failures:", file=sys.stderr)
        for error in fatal_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
