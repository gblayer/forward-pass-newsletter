"""OpenReview candidate fetcher (best-effort).

Uses the public API v2 full-text search over recent notes. OpenReview's
search is venue-heterogeneous and noisy — this stage is intentionally
permissive; the Claude relevance pass cleans it up. Failures are
non-fatal: the newsletter still ships from arXiv + HF.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from ..models import Paper

log = logging.getLogger(__name__)

API = "https://api2.openreview.net/notes/search"


def fetch(search_terms: list[str], since: datetime) -> list[Paper]:
    out: list[Paper] = []
    since_ms = int(since.timestamp() * 1000)
    for term in search_terms:
        try:
            r = requests.get(
                API,
                params={"term": term, "content": "all", "source": "forum", "limit": 50},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            for note in r.json().get("notes", []):
                cdate = note.get("cdate") or note.get("tcdate") or 0
                if cdate < since_ms:
                    continue
                content = note.get("content", {})

                def _val(key):
                    v = content.get(key, "")
                    return v.get("value", "") if isinstance(v, dict) else v

                title = str(_val("title")).strip()
                abstract = str(_val("abstract")).strip()
                if not title or not abstract:
                    continue
                authors = _val("authors") or []
                if isinstance(authors, dict):
                    authors = authors.get("value", [])
                forum = note.get("forum") or note.get("id")
                out.append(
                    Paper(
                        id=f"openreview:{forum}",
                        title=title,
                        abstract=abstract,
                        authors=list(authors) if isinstance(authors, list) else [],
                        url=f"https://openreview.net/forum?id={forum}",
                        published=datetime.fromtimestamp(cdate / 1000, tz=timezone.utc),
                        source="openreview",
                        matched_keyword=term,
                    )
                )
        except Exception as e:  # noqa: BLE001
            log.warning("OpenReview search failed for '%s': %s", term, e)
    log.info("OpenReview: %d candidates", len(out))
    return out
