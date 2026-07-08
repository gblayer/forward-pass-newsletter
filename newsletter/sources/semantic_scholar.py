"""Semantic Scholar (optional, needs S2_API_KEY for reliable rate limits).

Complements arXiv keyword/author sweeps with citation-graph discovery:
recent papers that CITE your seed papers are strong relevance candidates
even if they use unexpected vocabulary.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import requests

from ..models import Paper

log = logging.getLogger(__name__)

BASE = "https://api.semanticscholar.org/graph/v1"

# arXiv IDs of your seed papers (papers whose *new citers* you want to see).
SEED_ARXIV_IDS = [
    "2506.10707",  # ConTextTab
    "2505.18125",  # TabSTAR
    "2509.03505",  # LimiX
    "2511.02818",  # Orion-MSP
    "2505.10960",  # Relational Graph Transformer
    "2406.12031",  # Large-scale transfer learning via LM (TabuLa-8B)
    "2502.11596",  # LLM Embeddings for tabular DL
    "2511.15941",  # iLTM
    "2604.12596",  # KumoRFM-2
]

FIELDS = "title,abstract,authors,externalIds,publicationDate,url"


def _headers() -> dict:
    key = os.environ.get("S2_API_KEY", "")
    return {"x-api-key": key} if key else {}


def fetch_new_citers(since: datetime) -> list[Paper]:
    out: list[Paper] = []
    for aid in SEED_ARXIV_IDS:
        try:
            r = requests.get(
                f"{BASE}/paper/arXiv:{aid}/citations",
                params={"fields": FIELDS, "limit": 100, "sort": "publicationDate:desc"},
                headers=_headers(),
                timeout=30,
            )
            if r.status_code != 200:
                continue
            for item in r.json().get("data", []):
                p = item.get("citingPaper", {})
                pub = p.get("publicationDate")
                if not pub:
                    continue
                pub_dt = datetime.fromisoformat(pub).replace(tzinfo=timezone.utc)
                if pub_dt < since:
                    continue
                ext = p.get("externalIds") or {}
                arxiv_id = ext.get("ArXiv")
                pid = f"arxiv:{arxiv_id}" if arxiv_id else f"s2:{p.get('paperId')}"
                url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else p.get("url", "")
                out.append(
                    Paper(
                        id=pid,
                        title=p.get("title", ""),
                        abstract=p.get("abstract") or "",
                        authors=[a.get("name", "") for a in p.get("authors", [])],
                        url=url,
                        published=pub_dt,
                        source="s2",
                        matched_keyword=f"cites arXiv:{aid}",
                    )
                )
            time.sleep(1.5)
        except Exception as e:  # noqa: BLE001
            log.warning("S2 citations fetch failed for %s: %s", aid, e)
    log.info("Semantic Scholar: %d new citing papers", len(out))
    return out
