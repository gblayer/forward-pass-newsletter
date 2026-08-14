"""Subscriber list backed by Resend Audiences.

The static site's subscribe form posts to the Cloudflare Worker
(infra/subscribe-worker.js), which writes contacts into a Resend Audience.
At send time this module reads that audience back and builds per-recipient
unsubscribe links whose HMAC tokens the Worker verifies.

Env (all optional — everything degrades to the static NEWSLETTER_TO list):
  RESEND_API_KEY  read the contact list (Resend account-level /contacts API)
  UNSUB_SECRET    shared HMAC secret; MUST match the Worker's UNSUB_SECRET

The unsubscribe endpoint base URL comes from config.yaml → site.subscribe_endpoint.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from pathlib import Path

import requests
import yaml

log = logging.getLogger("newsletter.subscribers")

RESEND_API = "https://api.resend.com"

_CONFIG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text())


def endpoint() -> str:
    """Worker base URL (no trailing slash), or "" if not configured."""
    return (_CONFIG.get("site", {}).get("subscribe_endpoint") or "").rstrip("/")


def audience_recipients() -> list[str]:
    """Active (non-unsubscribed) contacts from Resend (account-level /contacts).

    Returns [] when the list isn't configured or the API call fails —
    the send then simply covers the static NEWSLETTER_TO list.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return []
    contacts: list[dict] = []
    after = None
    try:
        while True:  # paginated: max 100 per page
            params = {"limit": 100}
            if after:
                params["after"] = after
            resp = requests.get(
                f"{RESEND_API}/contacts",
                headers={"Authorization": f"Bearer {api_key}"},
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
            page = payload.get("data", [])
            contacts.extend(page)
            if not payload.get("has_more") or not page:
                break
            after = page[-1]["id"]
    except Exception as exc:  # noqa: BLE001 — a list outage must not kill the send
        log.warning("Could not fetch Resend contacts (%s); sending to static list only.", exc)
        return []
    return [c["email"].strip().lower() for c in contacts if not c.get("unsubscribed")]


def unsubscribe_url(email: str) -> str:
    """Per-recipient one-click unsubscribe URL, or "" if not configured.

    Token layout must match the Worker: HMAC-SHA256(UNSUB_SECRET, lowercased
    email) hex; email itself travels base64url-encoded without padding.
    """
    secret = os.environ.get("UNSUB_SECRET", "")
    base = endpoint()
    if not (secret and base):
        return ""
    norm = email.strip().lower()
    token = hmac.new(secret.encode(), norm.encode(), hashlib.sha256).hexdigest()
    packed = base64.urlsafe_b64encode(norm.encode()).decode().rstrip("=")
    return f"{base}/unsubscribe?e={packed}&t={token}"
