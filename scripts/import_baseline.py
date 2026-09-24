#!/usr/bin/env python3
"""Convert the user-supplied public profile Markdown to auditable JSON snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "input" / "initial_profiles.md"
OUTPUT = ROOT / "data"
CONFIG = ROOT / "config" / "authors.json"
PROFILE = "https://sinta.kemdiktisaintek.go.id/authors/profile/"
COLLECTIONS = ("scopus", "garuda", "google_scholar", "rama", "researches", "community_services", "iprs", "books")
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
YEAR = re.compile(r"^\s*(20\d\d|19\d\d)\b")


def text(s: str) -> str:
    return re.sub(r"\s+", " ", LINK.sub(lambda m: m.group(1), s)).strip()


def pages(source: str):
    matches = list(re.finditer(r"^SINTA ID\s*:\s*(\d+)\s*$", source, re.M | re.I))
    for i, match in enumerate(matches):
        # The author name is 7 lines above the identifier, with blank lines.
        before = source[:match.start()].splitlines()
        name = before[-6].strip("* ")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        # Remove the next author's heading/affiliation from this author's body.
        if i + 1 < len(matches):
            next_lines = source[match.end():end].splitlines()
            content = "\n".join(next_lines[:-7])
        else:
            content = source[match.end():end]
        yield match.group(1), name, content


def classify(title: str, details: list[str], url: str | None) -> str:
    if url:
        if "scopus.com/record/" in url:
            return "scopus"
        if "garuda.kemdiktisaintek.go.id/documents/" in url:
            return "garuda"
        if "scholar.google" in url:
            return "google_scholar"
        if "rama." in url:
            return "rama"
    info = " ".join(details)
    if "Inventor :" in info or "Nomor Permohonan :" in info:
        return "iprs"
    if "Category :" in info or "ISBN :" in info:
        return "books"
    if "Leader :" in info:
        if re.search(r"PENGABDIAN|\bPKM\b|PELATIHAN", info, re.I):
            return "community_services"
        return "researches"
    return "unclassified"


def parse_author(author_id: str, name: str, body: str, original: dict | None) -> dict:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    records = {kind: [] for kind in COLLECTIONS}
    leftovers = []
    candidates = []
    headings = {"scopus", "garuda", "google scholar", "googlescholar", "rama", "researches", "community services", "iprs", "books"}
    for i, para in enumerate(paragraphs):
        match = LINK.fullmatch(para)
        next_para = paragraphs[i + 1] if i + 1 < len(paragraphs) else ""
        if match and ("scopus.com/record/" in match.group(2) or "/documents/detail/" in match.group(2) or "scholar.google" in match.group(2) or "rama." in match.group(2)):
            candidates.append((i, match.group(1), match.group(2).replace("\\&", "&")))
        elif not match and not para.startswith(('-', '**', '[')) and para.lower() not in headings and re.match(r"^(Leader|Inventor|Category)\s*:", next_para, re.I):
            candidates.append((i, text(para), None))

    taken = set()
    for index, (start, title, url) in enumerate(candidates):
        end = candidates[index + 1][0] if index + 1 < len(candidates) else len(paragraphs)
        details = []
        for j in range(start + 1, end):
            p = paragraphs[j]
            if p.lower() in headings or p.startswith("- [") or p.startswith("**"):
                continue
            details.append(p)
            taken.add(j)
        taken.add(start)
        category = classify(title, details, url)
        if category == "unclassified":
            leftovers.append({"title": title, "details": details})
            continue
        year = next((int(m.group(1)) for p in reversed(details) if (m := YEAR.match(p))), None)
        fingerprint = (url or f"{category}|{title}").encode("utf-8")
        item = {
            "id": hashlib.sha256(fingerprint).hexdigest()[:20],
            "title": title,
            "url": url,
            "year": year,
            "source_page": PROFILE + author_id,
            "details": [text(p) for p in details],
        }
        # Keep additional bibliographic details exactly as supplied in Markdown.
        if url and "garuda." in url:
            doi = re.search(r"\bDOI\s*:\s*([^\s]+)", " ".join(details))
            item["doi"] = doi.group(1) if doi else None
        if category in ("researches", "community_services"):
            leader = re.search(r"Leader\s*:\s*(.+?)(?=\s{2,}|PENDANAAN|Penelitian|HIBAH|Pengabdian|$)", " ".join(details), re.I)
            item["leader"] = text(leader.group(1)) if leader else None
        records[category].append(item)

    for i, para in enumerate(paragraphs):
        if i not in taken and para.lower() not in headings and not para.startswith("- [") and para != "\\-":
            leftovers.append(text(para))

    profile = {
        "name": name, "sinta_id": author_id,
        "affiliation": "Institut Teknologi Sumatera",
        "affiliation_url": "https://sinta.kemdiktisaintek.go.id/affiliations/profile/537",
        "department": "S1 - Matematika",
        "department_url": "https://sinta.kemdiktisaintek.go.id/departments/profile/537/002014/44201",
        "avatar_url": None, "subjects": [], "scores": {},
    }
    if original:
        profile = original["profile"]
    snapshot = {"source": "input/initial_profiles.md", "collections": records, "unclassified": leftovers}
    result = original or {
        "schema_version": 2,
        "generated_at": None,
        "source": {"service": "SINTA - Science and Technology Index", "profile_url": PROFILE + author_id, "access": "user-supplied public first pages"},
        "configured_author": {"name": name.title(), "sinta_id": author_id, "profile_url": PROFILE + author_id, "enabled": True},
        "profile": profile,
        "collections": {}, "metrics": {}, "collection_status": {},
    }
    result["manual_baseline"] = snapshot
    for kind, items in records.items():
        if original and result["collections"].get(kind, {}).get("records"):
            continue
        result["collections"][kind] = {
            "view": {"google_scholar": "googlescholar", "community_services": "services"}.get(kind, kind),
            "scope": "user_supplied_public_first_pages", "pages_collected": 1 if items else 0,
            "reported_total": None, "records_collected": len(items),
            "public_access_limited": True, "records": items,
        }
        result["collection_status"][kind] = {"status": "manual_baseline" if items else "not_provided"}
    return result


def main():
    source = INPUT.read_text(encoding="utf-8")
    authors = list(pages(source))
    if len(authors) != 16 or len({entry[0] for entry in authors}) != 16:
        raise ValueError("Expected 16 unique SINTA IDs in the supplied Markdown")
    OUTPUT.mkdir(exist_ok=True)
    CONFIG.parent.mkdir(exist_ok=True)
    cfg, manifest = [], []
    for author_id, name, body in authors:
        path = OUTPUT / f"{author_id}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        result = parse_author(author_id, name, body, old)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cfg.append(result["configured_author"])
        manifest.append({"name": name, "sinta_id": author_id, "file": path.name,
                         "status": "manual_baseline", "counts": {key: len(value) for key, value in result["manual_baseline"]["collections"].items()}})
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "index.json").write_text(json.dumps({"schema_version": 2, "generated_at": None, "authors_count": len(authors), "authors": manifest}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(authors)} public author snapshots.")


if __name__ == "__main__":
    main()
