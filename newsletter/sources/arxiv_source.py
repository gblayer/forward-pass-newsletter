"""arXiv candidate fetcher.

Two strategies, merged:
1. Recent papers in the configured categories within the lookback window
   (broad sweep; keyword prefilter applied by the caller).
2. Direct author queries for every watchlist author (catches relevant
   papers that use none of the prefilter keywords).
"""
from __future__ import annotations

import time
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

from ..models import Paper

log = logging.getLogger(__name__)

API = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}


def _parse_feed(xml_text: str) -> list[Paper]:
    papers = []
    root = ET.fromstring(xml_text)
    for entry in root.findall("a:entry", NS):
        arxiv_id = entry.findtext("a:id", "", NS).split("/abs/")[-1]
        title = " ".join(entry.findtext("a:title", "", NS).split())
        abstract = " ".join(entry.findtext("a:summary", "", NS).split())
        authors = [a.findtext("a:name", "", NS) for a in entry.findall("a:author", NS)]
        published = entry.findtext("a:published", "", NS)
        updated = entry.findtext("a:updated", "", NS)
        cats = [c.get("term") for c in entry.findall("a:category", NS)]
        try:
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            pub_dt = datetime.now(timezone.utc)
        papers.append(
            Paper(
                id=f"arxiv:{arxiv_id.split('v')[0]}",
                title=title,
                abstract=abstract,
                authors=authors,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                published=pub_dt,
                source="arxiv",
                categories=[c for c in cats if c],
                is_new_version="v1" not in arxiv_id,
                updated=updated,
            )
        )
    return papers


def _query(search_query: str, max_results: int, sort_by: str = "submittedDate", start: int = 0) -> list[Paper]:
    params = {
        "search_query": search_query,
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return _parse_feed(r.text)
        except Exception as e:  # noqa: BLE001
            log.warning("arXiv query failed (attempt %d): %s", attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return []


def fetch_recent_by_category(
    categories: list[str], since: datetime, max_per_cat: int, hard_cap: int = 4000
) -> list[Paper]:
    """Broad sweep of everything submitted in `categories` since `since`.

    Results are sorted by submittedDate descending, so we page (page size
    `max_per_cat`) until a page reaches past the window boundary; `hard_cap`
    bounds total results per category for safety.
    """
    out: list[Paper] = []
    for cat in categories:
        fetched = 0
        kept_total = 0
        while fetched < hard_cap:
            papers = _query(f"cat:{cat}", max_per_cat, start=fetched)
            kept = [p for p in papers if p.published >= since]
            out.extend(kept)
            fetched += len(papers)
            kept_total += len(kept)
            time.sleep(3)  # arXiv API politeness
            # Stop when the page crossed the window boundary or results ran out.
            if len(kept) < len(papers) or len(papers) < max_per_cat:
                break
        log.info("arXiv %s: %d fetched, %d within window", cat, fetched, kept_total)
    return out


def fetch_by_authors(authors: list[str], since: datetime) -> list[Paper]:
    """Query each watchlist author; keep papers within the window."""
    out: list[Paper] = []
    for name in authors:
        # arXiv author search works best with 'lastname_firstinitial' but
        # plain quoted full-name queries are acceptable and simpler.
        q = f'au:"{name}"'
        papers = _query(q, 15)
        kept = [p for p in papers if p.published >= since]
        for p in kept:
            p.matched_author = name
        out.extend(kept)
        time.sleep(3)
    log.info("arXiv author watchlist: %d papers within window", len(out))
    return out
