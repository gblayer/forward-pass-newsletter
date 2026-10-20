"""HF Hub model watch — catch foundation models that debut on the Hub.

Some tabular / time-series foundation models appear on the Hugging Face Hub
as *model* repos (weights) without ever getting an arXiv paper or an HF *daily
paper* — so the paper pipeline (newsletter.main) never sees them. This module
lists models under the configured pipeline tags whose "Updated" (lastModified)
timestamp falls inside the SAME weekly window as the paper fetch, pre-loads
each one's card, and writes hf_models.json.

The routine then reads hf_models.json and, for each candidate, verifies the
OWNER and WHAT THE MODEL DOES via the card + web research, and includes it in
the industry section ONLY if it is a genuine tabular / time-series FOUNDATION
model — not a dataset-specific fine-tune, demo, or personal upload.

This file is recall-oriented (surface plausible candidates); the routine is
precision-oriented (reject the noise). hf_models.json is gitignored like
candidates.json.

    python -m newsletter.hf_models              # same window as the paper fetch
    python -m newsletter.hf_models --first-run  # 7-day backfill window
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import yaml

from .main import compute_window

log = logging.getLogger("newsletter.hf_models")

HF_API = "https://huggingface.co/api/models"
ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
_UA = {"User-Agent": "forward-pass-newsletter (+https://github.com/gblayer/forward-pass-newsletter)"}

# Name/tag substrings that hint at a generalist / pretrained tabular or
# time-series model (vs a one-off fine-tune). Used ONLY to float plausible
# candidates to the top of the capped list — never to auto-include. The
# routine still reads the card and researches the owner before deciding.
FM_HINTS = (
    "foundation", "pretrained", "pre-trained", "prior-fitted", "prior-data",
    "priors", "pfn", "tabpfn", "tabicl", "tab-icl", "in-context", "in_context",
    "icl", "zero-shot", "zeroshot", "few-shot", "fewshot", "generalist",
    "chronos", "moirai", "timesfm", "time-moe", "timemoe", "lag-llama",
    "tabdpt", "mitra", "orion", "tabula", "carte", "tabflex", "tabm",
    "tabular-foundation", "tabular foundation", "timeseries-foundation",
    "time-series-foundation", "forecasting-foundation", "exaone", "chakra",
)


# Match hints as whole tokens, so "tabula" does NOT fire on "tabular".
_FM_RE = re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(h) for h in FM_HINTS) + r")(?![a-z0-9])")


def _fm_signal(model: dict) -> bool:
    hay = " ".join([model.get("id", "")] + model.get("tags", [])).lower()
    return bool(_FM_RE.search(hay))


def _priority(model: dict) -> float:
    """Recall-oriented ranking: FM-looking repos first, then social traction."""
    score = 0.0
    if _fm_signal(model):
        score += 1000.0
    score += 3.0 * float(model.get("likes", 0) or 0)
    score += math.log1p(float(model.get("downloads", 0) or 0))
    return score


def _list_task(task: str, since, until, page_cap: int = 25) -> list[dict]:
    """Models for one pipeline tag whose lastModified is in [since, until).

    Listing is sorted by lastModified descending, so we stop paginating as
    soon as we cross below `since`.
    """
    out: list[dict] = []
    url = HF_API
    params = {"pipeline_tag": task, "sort": "lastModified", "direction": -1, "limit": 100}
    for _ in range(page_cap):
        try:
            resp = requests.get(url, params=params, headers=_UA, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — one task failing must not kill the rest
            log.warning("HF list failed for %s (%s)", task, exc)
            break
        batch = resp.json()
        if not batch:
            break
        stop = False
        for m in batch:
            lm = m.get("lastModified")
            if not lm:
                continue
            ts = _parse(lm)
            if ts is None:
                continue
            if ts < since:
                stop = True  # everything after this is older → done with this task
                break
            if ts < until:
                m["_pipeline_task"] = task
                out.append(m)
        nxt = _next_link(resp.headers.get("link", ""))
        if stop or not nxt:
            break
        url, params = nxt, None  # cursor URL already carries the query
    return out


def _parse(iso: str):
    from datetime import datetime, timezone

    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _next_link(link_header: str) -> str | None:
    # RFC5988: <url>; rel="next"
    for part in link_header.split(","):
        seg = part.strip()
        if seg.endswith('rel="next"') and "<" in seg:
            return seg[seg.index("<") + 1 : seg.index(">")]
    return None


def _card_excerpt(model_id: str, limit: int = 1400) -> str:
    """Best-effort README text so the routine can triage without a round trip."""
    for branch in ("main", "master"):
        try:
            r = requests.get(
                f"https://huggingface.co/{model_id}/raw/{branch}/README.md",
                headers=_UA, timeout=30,
            )
            if r.status_code == 200 and r.text.strip():
                text = r.text
                # Drop the YAML front-matter block if present.
                if text.lstrip().startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) == 3:
                        text = parts[2]
                text = " ".join(text.split())
                return text[:limit]
        except Exception:  # noqa: BLE001
            pass
    return ""


def gather(first_run: bool = False) -> dict:
    cfg = CONFIG.get("hf_hub_watch", {})
    tasks = cfg.get("tasks", [])
    cap = int(cfg.get("max_candidates", 60))
    since, until, window_label = compute_window(first_run=first_run)

    raw: dict[str, dict] = {}
    for task in tasks:
        for m in _list_task(task, since, until):
            prev = raw.get(m["id"])
            # A repo can carry several pipeline tags; keep one row, note tasks.
            if prev:
                prev.setdefault("_tasks", [prev["_pipeline_task"]])
                if task not in prev["_tasks"]:
                    prev["_tasks"].append(task)
            else:
                raw[m["id"]] = m

    ranked = sorted(raw.values(), key=_priority, reverse=True)[:cap]
    ranked.sort(key=lambda m: m.get("lastModified", ""), reverse=True)

    # Card READMEs dominate wall-clock — fetch them concurrently.
    with ThreadPoolExecutor(max_workers=8) as pool:
        cards = dict(zip(
            (m["id"] for m in ranked),
            pool.map(_card_excerpt, (m["id"] for m in ranked)),
        ))

    models = []
    for m in ranked:
        mid = m["id"]
        models.append({
            "id": mid,
            "author": mid.split("/")[0] if "/" in mid else mid,
            "url": f"https://huggingface.co/{mid}",
            "pipeline_tag": m.get("pipeline_tag"),
            "tasks": m.get("_tasks", [m.get("_pipeline_task")]),
            "last_modified": m.get("lastModified"),
            "created_at": m.get("createdAt"),
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "library_name": m.get("library_name"),
            "tags": [t for t in m.get("tags", []) if not t.startswith("region:")],
            "fm_signal": _fm_signal(m),
            "card_excerpt": cards.get(mid, ""),
        })

    return {
        "window_label": window_label,
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "total_in_window": len(raw),
        "returned": len(models),
        "models": models,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-run", action="store_true")
    args = parser.parse_args()

    if not CONFIG.get("hf_hub_watch", {}).get("enabled", False):
        log.info("hf_hub_watch disabled in config; writing empty list.")
        payload = {"window_label": "", "models": [], "total_in_window": 0, "returned": 0}
    else:
        payload = gather(first_run=args.first_run)
        log.info(
            "HF Hub watch: %d models updated in window (%s), returning top %d.",
            payload["total_in_window"], payload["window_label"], payload["returned"],
        )

    (ROOT / "hf_models.json").write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
