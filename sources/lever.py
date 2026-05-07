"""Lever public postings API.

API: https://api.lever.co/v0/postings/{slug}?mode=json
Stable identity: Lever posting `id` (UUID).
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from .base import Posting

log = logging.getLogger(__name__)


def fetch(slug: str, *, timeout: int = 30) -> Optional[list[dict]]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            log.info("lever: company '%s' not found", slug)
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.warning("lever: %s failed: %s", slug, e)
        return None


def parse(firm: str, jobs: list[dict]) -> list[Posting]:
    out: list[Posting] = []
    for j in jobs:
        ext = j.get("id")
        if not ext:
            continue
        cats = j.get("categories") or {}
        location = cats.get("location") or ""
        if isinstance(j.get("allLocations"), list) and not location:
            location = ", ".join(j["allLocations"])
        posted_ms = j.get("createdAt")
        out.append(
            Posting(
                firm=firm,
                external_id=str(ext),
                title=(j.get("text") or "").strip(),
                location=location or "",
                url=j.get("hostedUrl") or j.get("applyUrl") or "",
                source="lever",
                posted_at=str(posted_ms) if posted_ms else None,
            )
        )
    return out
