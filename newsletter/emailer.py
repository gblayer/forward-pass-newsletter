"""Build the HTML digest and send it over SMTP (Gmail app password works)."""
from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .models import Paper

SOURCE_BADGE = {
    "arxiv": ("arXiv", "#B31B1B"),
    "hf_daily": ("HF Daily", "#FF9D00"),
    "openreview": ("OpenReview", "#8B1A1A"),
    "s2": ("SemScholar", "#1857B6"),
}


def _paper_html(p: Paper) -> str:
    badge, color = SOURCE_BADGE.get(p.source, (p.source, "#666"))
    b = p.bullets or {}
    via = ""
    if p.matched_author:
        via = f'<span style="color:#888;font-size:12px;"> · via author watch: {p.matched_author}</span>'
    elif p.matched_keyword and p.matched_keyword.startswith("cites"):
        via = f'<span style="color:#888;font-size:12px;"> · {p.matched_keyword}</span>'
    version_note = ' <span style="color:#888;font-size:12px;">(updated version)</span>' if p.is_new_version else ""
    return f"""
    <div style="margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid #eee;">
      <div style="margin-bottom:6px;">
        <span style="background:{color};color:#fff;border-radius:3px;padding:1px 6px;
                     font-size:11px;vertical-align:middle;">{badge}</span>
        <span style="color:#888;font-size:12px;"> score {p.relevance_score}/10</span>{via}
      </div>
      <a href="{p.url}" style="font-size:16px;font-weight:600;color:#1a1a1a;
         text-decoration:none;">{p.title}</a>{version_note}
      <div style="color:#666;font-size:13px;margin:4px 0 10px;">{p.short_authors()}</div>
      <ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.5;color:#333;">
        <li><b>Problem:</b> {b.get('problem','')}</li>
        <li><b>Method:</b> {b.get('method','')}</li>
        <li><b>Limitations:</b> {b.get('limitations','')}</li>
      </ul>
      <div style="margin-top:8px;"><a href="{p.url}" style="font-size:13px;color:#1857B6;">→ paper</a></div>
    </div>"""


def _section_header(text: str) -> str:
    return (
        f'<h3 style="font-weight:600;font-size:15px;color:#1a1a1a;margin:32px 0 12px;'
        f'padding-bottom:6px;border-bottom:2px solid #1a1a1a;">{text}</h3>'
    )


def _industry_html(items: list[dict]) -> str:
    rows = []
    for it in items:
        company = (it.get("company") or "").strip()
        headline = (it.get("headline") or "").strip()
        date = (it.get("date") or "").strip()
        url = (it.get("url") or "").strip()
        summary = (it.get("summary") or "").strip()
        title_html = (
            f'<a href="{url}" style="color:#1a1a1a;text-decoration:none;">{headline}</a>'
            if url else headline
        )
        date_html = f'<span style="color:#888;font-size:12px;"> · {date}</span>' if date else ""
        rows.append(
            f"""
        <div style="margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid #eee;">
          <div style="margin-bottom:4px;">
            <span style="background:#0B7285;color:#fff;border-radius:3px;padding:1px 6px;
                         font-size:11px;">{company}</span>{date_html}
          </div>
          <div style="font-size:15px;font-weight:600;">{title_html}</div>
          <div style="color:#333;font-size:14px;line-height:1.5;margin-top:4px;">{summary}</div>
        </div>"""
        )
    return "".join(rows)


def _spotlight_html(spotlight: dict) -> str:
    theme = (spotlight.get("theme") or "").strip()
    body = (spotlight.get("body") or "").strip()
    if not body:
        return ""
    return f"""
    <div style="margin:32px 0;padding:16px 18px;background:#f6f8fa;border-radius:6px;
                border-left:4px solid #6741D9;">
      <div style="font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:#6741D9;
                  font-weight:600;margin-bottom:6px;">🔬 Spotlight · {theme}</div>
      <div style="font-size:14px;line-height:1.55;color:#333;">{body}</div>
    </div>"""


def build_html(
    papers: list[Paper],
    window_label: str,
    industry: list[dict] | None = None,
    spotlight: dict | None = None,
    name: str = "Context Window",
    tagline: str = "Your daily window into tabular ML & foundation models",
) -> str:
    if papers:
        academic_block = _section_header("📄 Academic — new papers") + "".join(
            _paper_html(p) for p in papers
        )
        intro = f"{len(papers)} paper{'s' if len(papers) != 1 else ''} matched your profile ({window_label})."
    else:
        academic_block = ""
        intro = f"No new relevant papers in the {window_label}. Quiet day — enjoy the coffee. ☕"

    industry_block = ""
    if industry:
        industry_block = _section_header("🏢 Industry — this week") + _industry_html(industry)

    # Spotlight leads the issue (top), then the academic papers, then industry.
    spotlight_block = _spotlight_html(spotlight) if spotlight else ""

    return f"""
    <div style="max-width:640px;margin:0 auto;font-family:-apple-system,Segoe UI,Roboto,sans-serif;">
      <h2 style="font-weight:600;margin-bottom:2px;">📊 {name}</h2>
      <div style="color:#888;font-size:13px;margin-bottom:10px;">{tagline}</div>
      <p style="color:#555;font-size:14px;">{intro}</p>
      {spotlight_block}
      {academic_block}
      {industry_block}
      <p style="color:#aaa;font-size:12px;margin-top:28px;">Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
      · edit config.yaml in the repo to tune topics, authors and volume.</p>
    </div>"""


def send(html: str, subject: str, smtp_host: str, smtp_port: int) -> None:
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    # NEWSLETTER_TO may be a single address or a comma/semicolon-separated list.
    raw_to = os.environ["NEWSLETTER_TO"]
    recipients = [addr.strip() for addr in raw_to.replace(";", ",").split(",") if addr.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    # Show only the sender in the visible To: header (keeps subscribers private);
    # actual delivery uses the full recipient list below.
    msg["To"] = user
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, recipients, msg.as_string())
