"""ATS auto-detection from a firm's careers page.

Fetch the URL, grep the HTML for known ATS embed patterns. Cache the
result per firm in firms_detected.json so we don't re-detect every run.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import requests

log = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).resolve().parent / "firms_detected.json"

ATS = Literal["greenhouse", "lever", "ashby", "workday", None]


@dataclass(frozen=True)
class Detection:
    ats: Optional[str]
    slug: Optional[str]
    extra: Optional[str] = None  # e.g. workday tenant subdomain


_PATTERNS = [
    # Greenhouse embed or job-board URL. Skip the literal "embed" placeholder so
    # we don't latch onto template HTML that uses it as a variable name.
    (
        "greenhouse",
        re.compile(
            r"(?:boards(?:-api)?\.greenhouse\.io|job-boards\.greenhouse\.io)"
            r"/(?:embed/job_board\?for=)?([a-z0-9][a-z0-9-]*)",
            re.IGNORECASE,
        ),
    ),
    ("lever", re.compile(r"jobs\.lever\.co/([a-z0-9][a-z0-9-]*)", re.IGNORECASE)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-z0-9][a-z0-9-]*)", re.IGNORECASE)),
    (
        "workday",
        re.compile(
            r"([a-z0-9-]+)\.(?:wd[0-9]+\.)?myworkdayjobs\.com/(?:[a-z]{2,5}/)?([a-z0-9-]+)",
            re.IGNORECASE,
        ),
    ),
]

_BAD_GREENHOUSE_SLUGS = {"embed", "v1", "boards"}
_BAD_LEVER_SLUGS = {"v0", "postings"}


def load_cache() -> dict[str, dict]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except json.JSONDecodeError:
            log.warning("detect: cache corrupt, reseeding")
    return {}


def save_cache(cache: dict[str, dict]) -> None:
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))


def detect(careers_url: str, *, timeout: int = 20) -> Detection:
    """Sniff the careers page HTML for an ATS embed pattern."""
    try:
        resp = requests.get(
            careers_url,
            timeout=timeout,
            headers={"User-Agent": "q27bot/1.0 (+intern monitor)"},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        log.info("detect: fetch failed for %s: %s", careers_url, e)
        return Detection(None, None)

    html = resp.text
    for ats, pattern in _PATTERNS:
        m = pattern.search(html)
        if not m:
            continue
        if ats == "workday":
            return Detection(ats="workday", slug=m.group(2), extra=m.group(1))
        slug = m.group(1).lower()
        if ats == "greenhouse" and slug in _BAD_GREENHOUSE_SLUGS:
            continue
        if ats == "lever" and slug in _BAD_LEVER_SLUGS:
            continue
        return Detection(ats=ats, slug=slug)
    return Detection(None, None)


def detect_with_cache(
    firm_name: str,
    careers_url: Optional[str],
    cache: dict[str, dict],
    *,
    override_ats: Optional[str] = None,
    override_slug: Optional[str] = None,
) -> Detection:
    """Resolve a firm to an ATS+slug.

    Precedence: explicit override (skip HTTP entirely) → cache → fresh fetch.
    Overrides are recorded in the cache too so removing them from firms.yaml
    doesn't trigger a re-detect on the next run.
    """
    if override_ats and override_slug:
        d = Detection(ats=override_ats, slug=override_slug)
        cache[firm_name] = {"ats": d.ats, "slug": d.slug, "extra": None, "source": "override"}
        return d
    if not careers_url:
        return Detection(None, None)
    if firm_name in cache:
        c = cache[firm_name]
        return Detection(c.get("ats"), c.get("slug"), c.get("extra"))
    d = detect(careers_url)
    cache[firm_name] = {"ats": d.ats, "slug": d.slug, "extra": d.extra, "careers_url": careers_url}
    return d
