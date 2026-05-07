"""Greenhouse public job board API.

API: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Stable identity: numeric `id` from Greenhouse.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from .base import Posting

log = logging.getLogger(__name__)


def fetch(slug: str, *, timeout: int = 30) -> Optional[list[dict]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            log.info("greenhouse: board '%s' not found", slug)
            return None
        resp.raise_for_status()
        return resp.json().get("jobs", [])
    except requests.RequestException as e:
        log.warning("greenhouse: %s failed: %s", slug, e)
        return None


def parse(firm: str, jobs: list[dict]) -> list[Posting]:
    out: list[Posting] = []
    for j in jobs:
        ext = j.get("id")
        if ext is None:
            continue
        location = ""
        loc = j.get("location")
        if isinstance(loc, dict):
            location = loc.get("name", "") or ""
        elif isinstance(loc, str):
            location = loc
        out.append(
            Posting(
                firm=firm,
                external_id=str(ext),
                title=(j.get("title") or "").strip(),
                location=location,
                url=j.get("absolute_url", ""),
                source="greenhouse",
                posted_at=j.get("updated_at") or j.get("first_published"),
            )
        )
    return out
