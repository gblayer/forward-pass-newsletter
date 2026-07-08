"""HuggingFace Daily Papers.

Every paper featured on HF Daily within the window becomes a candidate
(no keyword prefilter needed — Claude decides relevance downstream).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

from ..models import Paper

log = logging.getLogger(__name__)

API = "https://huggingface.co/api/daily_papers"


def fetch(since: datetime) -> list[Paper]:
    out: list[Paper] = []
    day = since.date()
    today = datetime.now(timezone.utc).date()
    while day <= today:
        try:
            r = requests.get(API, params={"date": day.isoformat()}, timeout=30)
            if r.status_code == 200:
                for item in r.json():
                    p = item.get("paper", {})
                    arxiv_id = p.get("id", "")
                    if not arxiv_id:
                        continue
                    pub = p.get("publishedAt") or item.get("publishedAt") or ""
                    try:
                        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    except ValueError:
                        pub_dt = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
                    out.append(
                        Paper(
                            id=f"arxiv:{arxiv_id}",
                            title=p.get("title", "").strip(),
                            abstract=p.get("summary", "").strip(),
                            authors=[a.get("name", "") for a in p.get("authors", [])],
                            url=f"https://arxiv.org/abs/{arxiv_id}",
                            published=pub_dt,
                            source="hf_daily",
                        )
                    )
        except Exception as e:  # noqa: BLE001
            log.warning("HF daily fetch failed for %s: %s", day, e)
        day += timedelta(days=1)
    log.info("HF daily papers: %d candidates", len(out))
    return out
