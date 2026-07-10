"""Render a sample issue to preview.html for design work — offline, no
network, no API, no email. Edit the styling in emailer.py, then:

    python -m newsletter.preview      # writes preview.html
    open preview.html                 # (macOS)  — refresh after each edit

The sample below exercises every part of the layout (In-brief bullets,
several paper cards with all four fields, an updated-version note, both
arXiv and HF sources, and the industry section) so you can see the full
design at once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .emailer import build_html
from .models import Paper


def _p(title, authors, score, source, bullets, is_new_version=False, matched_author=None):
    p = Paper(
        id="arxiv:2607.00000",
        title=title,
        abstract="",
        authors=authors,
        url="https://arxiv.org/abs/2607.00000",
        published=datetime.now(timezone.utc),
        source=source,
        is_new_version=is_new_version,
        matched_author=matched_author,
    )
    p.relevance_score = score
    p.bullets = bullets
    return p


SAMPLE_PAPERS = [
    _p(
        "TabPack: Efficient Hyperparameter Ensembles for Tabular Deep Learning",
        ["Yury Gorishniy", "Akim Kotelnikov", "Ivan Rubachev", "Artem Babenko"],
        9, "arxiv",
        {
            "problem": "MLP ensembles are strong for tabular data but still need per-dataset hyperparameter tuning to peak.",
            "method": "One run samples many MLPs from user-given hyperparameter ranges, trains them in parallel, and picks members on the fly.",
            "results": "On medium-to-large datasets, default TabPack matches extensively tuned prior methods at a fraction of the compute.",
            "limitations": "Likely: behaviour on very small or heavily categorical data is unclear; gains are parity, not a clear win.",
        },
        matched_author="Yury Gorishniy",
    ),
    _p(
        "A Fair Benchmarking of Deep Relational Database Learning Models",
        ["Kazi F. Akhter", "Bharath Ajendla", "Manar D. Samad"],
        8, "arxiv",
        {
            "problem": "Deep RDB methods are evaluated under inconsistent protocols, making fair comparison impossible.",
            "method": "Refactors deep RDB models into a common framework, evaluated on five databases (classification + regression each).",
            "results": "Relational transformers rank best; deep RDB models beat TabPFN 2.5 even single-table; neighbour hops help.",
            "limitations": "Five databases with one task pair each is modest; results tied to the refactored implementations.",
        },
    ),
    _p(
        "Induction Heads and In-Context Learning in Tabular Foundation Models",
        ["A. Researcher", "B. Coauthor"],
        7, "hf_daily",
        {
            "problem": "How TabPFN-style models actually learn in context is poorly characterized.",
            "method": "Probes the attention circuits of a prior-fitted network on controlled synthetic tabular tasks.",
            "results": "Likely: identifies a soft context-matching estimator that interpolates across neighbours.",
            "limitations": "Synthetic setups; transfer to production TFMs is by analogy.",
        },
        is_new_version=True,
    ),
]

SAMPLE_INDUSTRY = [
    {
        "company": "Google / DeepMind",
        "headline": "TabFM lands in BigQuery via AI.PREDICT",
        "date": "2026-07-10",
        "url": "https://research.google/blog/",
        "summary": "Zero-shot tabular prediction now callable as a SQL function in the warehouse, no per-table training.",
    },
]

SAMPLE_SPOTLIGHT = {
    "theme": "relational / enterprise databases",
    "academia": [
        "TabPack matches tuned MLP ensembles in a single run.",
        "Deep RDB models beat TabPFN 2.5 on a fair five-database benchmark.",
    ],
    "industry": [
        "Google ships TabFM into BigQuery AI.PREDICT.",
    ],
}


def main() -> None:
    html = build_html(
        SAMPLE_PAPERS, "last 24 hours",
        industry=SAMPLE_INDUSTRY, spotlight=SAMPLE_SPOTLIGHT,
    )
    Path("preview.html").write_text(html)
    print("wrote preview.html — open it in a browser (refresh after each edit)")


if __name__ == "__main__":
    main()
