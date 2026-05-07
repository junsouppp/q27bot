"""northwesternfintech/2027QuantInternships source.

The repo stores one YAML file per firm under data/. Each file has:
    name, website, locations, notes, roles: [{role_type, links: [{url}]}]

Stable identity: roles do not have IDs, so we key on the URL itself.
Title is synthesized from role_type + a humanized URL slug since titles
aren't stored explicitly (the link points to the firm's own job page).
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import unquote, urlparse

import requests
import yaml

from .base import Posting

log = logging.getLogger(__name__)

_ROLE_TYPE_NAMES = {
    "QT": "Quantitative Trader",
    "QR": "Quantitative Researcher",
    "QD": "Quantitative Developer",
    "SWE": "Software Engineer",
    "SDE": "Software Engineer",
}


def _list_files(api_url: str, *, timeout: int = 30) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    resp = requests.get(api_url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    return [f for f in resp.json() if f.get("name", "").endswith(".yaml") and f["name"] != "README.md"]


def _fetch_yaml(url: str, *, timeout: int = 30) -> Optional[dict]:
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return yaml.safe_load(resp.text)
    except (requests.RequestException, yaml.YAMLError) as e:
        log.warning("northwestern: failed to fetch %s: %s", url, e)
        return None


def _slug_to_title(url: str) -> str:
    """Pull a human-readable hint from the URL path's last segment."""
    try:
        path = urlparse(url).path
        last = unquote(path.rstrip("/").rsplit("/", 1)[-1])
        # Drop trailing IDs like "10717" or query-style suffixes
        last = re.sub(r"[-_]?\d{4,}$", "", last)
        words = re.split(r"[-_]+", last)
        return " ".join(w for w in words if w and not w.isdigit()).title()
    except Exception:  # pragma: no cover
        return ""


def fetch(api_url: str, *, max_workers: int = 5, timeout: int = 30) -> list[dict]:
    """Returns list of (filename, parsed_yaml) — preserved as dicts for parse()."""
    try:
        files = _list_files(api_url, timeout=timeout)
    except requests.RequestException as e:
        log.warning("northwestern: directory listing failed: %s", e)
        return []

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(_fetch_yaml, f["download_url"], timeout=timeout): f["name"]
            for f in files
            if f.get("download_url")
        }
        for fut in as_completed(futs):
            data = fut.result()
            if data is not None:
                data["_filename"] = futs[fut]
                results.append(data)
    log.info("northwestern: parsed %d firm files", len(results))
    return results


def parse(firm_yamls: list[dict]) -> list[Posting]:
    out: list[Posting] = []
    for entry in firm_yamls:
        firm = (entry.get("name") or "").strip() or _filename_to_firm(entry.get("_filename", ""))
        location = (entry.get("locations") or "").strip()
        roles = entry.get("roles") or []
        if not isinstance(roles, list):
            continue
        for role in roles:
            if not isinstance(role, dict):
                continue
            # Skip rows explicitly marked closed/inactive.
            status = str(role.get("status", "")).lower()
            if status in {"closed", "inactive", "filled"}:
                continue
            role_type = role.get("role_type") or ""
            role_label = _ROLE_TYPE_NAMES.get(role_type, role_type or "Role")
            for link in role.get("links") or []:
                if not isinstance(link, dict):
                    continue
                url = link.get("url")
                if not url:
                    continue
                slug_hint = _slug_to_title(url)
                title = f"{role_label} Intern" if not slug_hint else f"{role_label} Intern - {slug_hint}"
                out.append(
                    Posting(
                        firm=firm,
                        external_id=url,  # URL-as-ID per spec
                        title=title,
                        location=location,
                        url=url,
                        source="northwestern",
                        posted_at=None,
                    )
                )
    return out


def _filename_to_firm(name: str) -> str:
    base = re.sub(r"\.ya?ml$", "", name)
    return base.replace("-", " ").title()
