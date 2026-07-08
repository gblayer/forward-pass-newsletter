"""Stage 2: Claude decides relevance against the topic profile (batched,
cheap model), then writes pedagogical 3-bullet summaries for the keepers.
"""
from __future__ import annotations

import json
import logging
import os

import anthropic

from .models import Paper

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ---------------------------------------------------------------- filtering

FILTER_SYSTEM = """You are a research-paper triage assistant for a PhD student.
You will receive the student's topic profile and a numbered batch of papers
(title + abstract). For EACH paper, judge how relevant it is to the profile.

Scoring: 0 = clearly unrelated; 3 = tangential; 6 = adjacent and likely
interesting; 8 = squarely on-topic; 10 = must-read. Be generous with
adjacent-but-connected work (the profile explicitly wants breadth), but
strict with papers that merely apply off-the-shelf tabular models to a
domain problem without methodological contribution.

Respond ONLY with a JSON array, one object per paper, no markdown fences:
[{"i": <paper number>, "score": <0-10>, "reason": "<max 15 words>"}]"""


def score_batch(papers: list[Paper], topic_profile: str, model: str) -> None:
    numbered = "\n\n".join(
        f"[{i}] TITLE: {p.title}\nABSTRACT: {p.abstract[:1200]}"
        for i, p in enumerate(papers)
    )
    msg = client().messages.create(
        model=model,
        max_tokens=2000,
        system=FILTER_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"TOPIC PROFILE:\n{topic_profile}\n\nPAPERS:\n{numbered}",
        }],
    )
    text = msg.content[0].text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        for item in json.loads(text):
            i = item.get("i")
            if isinstance(i, int) and 0 <= i < len(papers):
                papers[i].relevance_score = int(item.get("score", 0))
                papers[i].relevance_reason = item.get("reason", "")
    except json.JSONDecodeError:
        log.error("Could not parse filter response: %s", text[:300])


def filter_papers(papers: list[Paper], topic_profile: str, model: str,
                  batch_size: int = 20, threshold: int = 6) -> list[Paper]:
    for start in range(0, len(papers), batch_size):
        score_batch(papers[start:start + batch_size], topic_profile, model)
    kept = [p for p in papers if p.relevance_score >= threshold]
    kept.sort(key=lambda p: p.relevance_score, reverse=True)
    log.info("Relevance filter: %d/%d papers kept (threshold %d)",
             len(kept), len(papers), threshold)
    return kept


# ---------------------------------------------------------------- summaries

SUMMARY_SYSTEM = """You write short, pedagogical paper digests for a PhD
student in tabular machine learning. They know the field well (TabPFN,
tabular ICL, LLM embeddings, relational FMs), so be precise, not vague.

For the given paper, respond ONLY with a JSON object, no markdown fences:
{
  "problem": "<1-2 sentences: the problem/goal, and why it matters>",
  "method": "<1-2 sentences: the core method/idea, named concretely>",
  "limitations": "<1-2 sentences: honest limitations or open questions —
                  from the abstract if stated, otherwise your informed
                  reading (prefix with 'Likely:' when inferred)>"
}
Plain language, no hype words, max ~40 words per field."""


def summarize(paper: Paper, model: str) -> None:
    msg = client().messages.create(
        model=model,
        max_tokens=500,
        system=SUMMARY_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"TITLE: {paper.title}\nAUTHORS: {paper.short_authors(8)}\n"
                       f"ABSTRACT: {paper.abstract[:2500]}",
        }],
    )
    text = msg.content[0].text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        paper.bullets = json.loads(text)
    except json.JSONDecodeError:
        paper.bullets = {"problem": paper.abstract[:200] + "…", "method": "", "limitations": ""}
