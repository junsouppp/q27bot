"""Ashby public job-board API.

API: https://api.ashbyhq.com/posting-api/job-board/{slug}
Stable identity: Ashby `id` (UUID). Note: spec listed a typo'd path
("postingob-board"); the canonical endpoint is `posting-api/job-board`.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from .base import Posting

log = logging.getLogger(__name__)


def fetch(slug: str, *, timeout: int = 30) -> Optional[list[dict]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            log.info("ashby: board '%s' not found", slug)
            return None
        resp.raise_for_status()
        body = resp.json()
        return body.get("jobs", []) if isinstance(body, dict) else []
    except requests.RequestException as e:
        log.warning("ashby: %s failed: %s", slug, e)
        return None


def parse(firm: str, jobs: list[dict]) -> list[Posting]:
    out: list[Posting] = []
    for j in jobs:
        ext = j.get("id")
        if not ext:
            continue
        location = j.get("location") or j.get("locationName") or ""
        if not location and isinstance(j.get("secondaryLocations"), list):
            location = ", ".join(s.get("location", "") for s in j["secondaryLocations"] if s)
        out.append(
            Posting(
                firm=firm,
                external_id=str(ext),
                title=(j.get("title") or "").strip(),
                location=location,
                url=j.get("jobUrl") or j.get("applyUrl") or "",
                source="ashby",
                posted_at=j.get("publishedAt") or j.get("updatedAt"),
            )
        )
    return out
