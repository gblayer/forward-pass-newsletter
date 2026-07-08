from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Paper:
    id: str                      # stable dedup key, e.g. "arxiv:2506.10707"
    title: str
    abstract: str
    authors: list[str]
    url: str
    published: datetime
    source: str                  # arxiv | hf_daily | openreview | s2
    categories: list[str] = field(default_factory=list)
    matched_author: str | None = None   # set when found via author watchlist
    matched_keyword: str | None = None  # set when found via keyword prefilter
    is_new_version: bool = False        # arXiv v2+ (updated, not brand new)
    updated: str = ""
    # Filled by the Claude relevance pass:
    relevance_score: int = 0            # 0-10
    relevance_reason: str = ""
    # Filled by the Claude summary pass:
    bullets: dict | None = None         # {problem, method, limitations}

    def short_authors(self, n: int = 4) -> str:
        if len(self.authors) <= n:
            return ", ".join(self.authors)
        return ", ".join(self.authors[:n]) + f" (+{len(self.authors) - n})"
