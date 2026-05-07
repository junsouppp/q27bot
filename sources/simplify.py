"""SimplifyJobs Summer 2027 (or 2026 fallback) listings.json source.

Stable identity: SimplifyJobs assigns each posting a UUID `id`; we use it.
Reject inactive (`active=false`) or hidden (`is_visible=false`) entries —
those represent closed/removed roles.
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

from .base import Posting

log = logging.getLogger(__name__)


def fetch(primary_url: str, fallback_url: str, *, timeout: int = 30) -> list[dict]:
    for url in (primary_url, fallback_url):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 404:
                log.info("simplify: %s 404, trying next", url)
                continue
            resp.raise_for_status()
            data = resp.json()
            log.info("simplify: %d entries from %s", len(data), url)
            return data
        except requests.RequestException as e:
            log.warning("simplify: %s failed: %s", url, e)
    return []


def parse(entries: Iterable[dict]) -> list[Posting]:
    out: list[Posting] = []
    for e in entries:
        if not e.get("active", True):
            continue
        if e.get("is_visible") is False:
            continue
        ext = e.get("id")
        if not ext:
            continue
        firm = (e.get("company_name") or "").strip()
        title = (e.get("title") or "").strip()
        url = e.get("url") or ""
        locs = e.get("locations") or []
        location = ", ".join(locs) if isinstance(locs, list) else str(locs)
        posted = e.get("date_posted")
        out.append(
            Posting(
                firm=firm,
                external_id=str(ext),
                title=title,
                location=location,
                url=url,
                source="simplify",
                posted_at=str(posted) if posted else None,
            )
        )
    return out
