"""Seen-paper store: a flat JSON file committed back to the repo by CI,
so overlapping lookback windows never resend the same paper."""
from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent.parent / "seen_papers.json"


def load_seen() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_seen(seen: set[str], keep_last: int = 5000) -> None:
    ids = sorted(seen)[-keep_last:]
    STATE_FILE.write_text(json.dumps(ids, indent=0))
