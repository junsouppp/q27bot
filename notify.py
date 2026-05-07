"""Discord webhook notifier.

- Caps embeds at 10 per request (Discord hard limit).
- Respects 429 retry_after.
- For dry-run, prints what would be sent and never hits the wire.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

import requests

from sources.base import Posting

log = logging.getLogger(__name__)

EMBED_BATCH = 10
_COLOR_BY_SOURCE = {
    "greenhouse": 0x2EB37C,
    "lever": 0x5C45CC,
    "ashby": 0xE0457B,
    "simplify": 0x4A8AE5,
    "northwestern": 0x9B59B6,
}


def _embed(p: Posting) -> dict:
    return {
        "title": (p.title or "Posting")[:256],
        "url": p.url,
        "description": f"**{p.firm}**" + (f" — {p.location}" if p.location else ""),
        "color": _COLOR_BY_SOURCE.get(p.source, 0x95A5A6),
        "footer": {"text": f"source: {p.source}"},
    }


def send_postings(
    webhook_url: str,
    postings: Iterable[Posting],
    *,
    dry_run: bool = False,
    session: requests.Session | None = None,
) -> int:
    items = list(postings)
    if not items:
        return 0
    sess = session or requests.Session()
    sent = 0
    for i in range(0, len(items), EMBED_BATCH):
        batch = items[i : i + EMBED_BATCH]
        payload = {"embeds": [_embed(p) for p in batch]}
        if dry_run:
            for p in batch:
                print(f"[would notify] {p.firm} | {p.title} | {p.url}")
            sent += len(batch)
            continue
        _post_with_retry(sess, webhook_url, payload)
        sent += len(batch)
    return sent


def send_text(
    webhook_url: str,
    content: str,
    *,
    dry_run: bool = False,
    session: requests.Session | None = None,
) -> None:
    if dry_run:
        print(f"[would post] {content}")
        return
    sess = session or requests.Session()
    _post_with_retry(sess, webhook_url, {"content": content[:2000]})


def _post_with_retry(sess: requests.Session, url: str, payload: dict, *, max_attempts: int = 5) -> None:
    """Best-effort POST. Connection / timeout errors are logged, never raised:
    we'd rather lose a Discord ping than abort the run before save_state."""
    for attempt in range(max_attempts):
        try:
            resp = sess.post(url, json=payload, timeout=20)
        except requests.RequestException as e:
            log.error("discord: post failed (%s)", e)
            return
        if resp.status_code == 429:
            try:
                wait = float(resp.json().get("retry_after", 1.0))
            except Exception:
                wait = 1.0
            log.info("discord: 429, sleeping %.2fs", wait)
            time.sleep(min(wait, 10.0))
            continue
        if 500 <= resp.status_code < 600:
            log.warning("discord: %d, retrying", resp.status_code)
            time.sleep(2 ** attempt)
            continue
        if not resp.ok:
            log.error("discord: %d %s", resp.status_code, resp.text[:200])
            return
        return
    log.error("discord: gave up after %d attempts", max_attempts)
