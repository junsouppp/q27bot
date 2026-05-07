"""Entry point for the Summer 2027 quant intern monitor.

Run order:
  1. Load firms.yaml + filter rules.
  2. Fetch SimplifyJobs and Northwestern in parallel (high-recall).
  3. Run ATS detection (cached) for each firm with a careers_url.
  4. Fetch Greenhouse/Lever/Ashby in parallel (max 5 concurrent).
  5. Filter by title.
  6. Diff against state/postings.json.
  7. Notify Discord; commit-back is handled by the workflow.

Flags:
  --dry-run   : hit real APIs, print would-notify, don't post or write state.
  --seed      : populate state without notifications, send one summary message.
                Workflow auto-passes this when state file is missing.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

import detect
import notify
from filters import FilterRules, title_passes
from sources import ashby, greenhouse, lever, northwestern, simplify
from sources.base import Posting

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state" / "postings.json"
UNSUPPORTED_LOG = ROOT / "unsupported.log"

log = logging.getLogger("q27bot")


# ---------- state ----------


def load_state() -> dict:
    if not STATE_PATH.exists() or STATE_PATH.stat().st_size == 0:
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        log.warning("state: corrupt JSON, treating as empty")
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def diff(current: list[Posting], previous: dict) -> tuple[list[Posting], list[str], dict]:
    """Compare current postings to previous state.

    Returns (new_postings, gone_keys, updated_state).
    `gone` keeps records in state with last_seen stamped — never deleted.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    current_by_key = {p.key(): p for p in current}
    new_state = dict(previous)  # shallow copy

    new_postings: list[Posting] = []
    for key, p in current_by_key.items():
        if key not in previous:
            new_postings.append(p)
            new_state[key] = {**p.to_dict(), "first_seen": now, "last_seen": now}
        else:
            prev = previous[key]
            new_state[key] = {**prev, **p.to_dict(), "last_seen": now}

    gone: list[str] = []
    for key in previous:
        if key not in current_by_key:
            gone.append(key)
            entry = dict(previous[key])
            entry.setdefault("last_seen", entry.get("first_seen", now))
            new_state[key] = entry

    return new_postings, gone, new_state


# ---------- fetch ----------


def fetch_community(cfg: dict) -> list[Posting]:
    s_cfg = cfg["sources"]["simplify"]
    n_cfg = cfg["sources"]["northwestern"]

    out: list[Posting] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_simp = pool.submit(simplify.fetch, s_cfg["primary"], s_cfg["fallback"])
        f_nu = pool.submit(northwestern.fetch, n_cfg["api"])
        try:
            out.extend(simplify.parse(f_simp.result()))
        except Exception as e:
            log.exception("simplify fetch failed: %s", e)
        try:
            out.extend(northwestern.parse(f_nu.result()))
        except Exception as e:
            log.exception("northwestern fetch failed: %s", e)
    return out


def fetch_one_firm(firm: dict, cache: dict) -> tuple[str, list[Posting], Optional[str]]:
    """Returns (firm_name, postings, error_msg). error_msg is non-None on failure."""
    name = firm["name"]
    careers = firm.get("careers_url")
    override_ats = firm.get("ats")
    override_slug = firm.get("slug")
    if not careers and not (override_ats and override_slug):
        return name, [], None  # nothing to do — already accounted for in firm list
    try:
        det = detect.detect_with_cache(
            name, careers, cache, override_ats=override_ats, override_slug=override_slug
        )
    except Exception as e:
        return name, [], f"detect error: {e}"

    try:
        if det.ats == "greenhouse":
            jobs = greenhouse.fetch(det.slug)
            if jobs is None:
                return name, [], None
            return name, greenhouse.parse(name, jobs), None
        if det.ats == "lever":
            jobs = lever.fetch(det.slug)
            if jobs is None:
                return name, [], None
            return name, lever.parse(name, jobs), None
        if det.ats == "ashby":
            jobs = ashby.fetch(det.slug)
            if jobs is None:
                return name, [], None
            return name, ashby.parse(name, jobs), None
        if det.ats == "workday":
            return name, [], "workday: needs implementation"
        return name, [], "unsupported"
    except Exception as e:
        return name, [], f"fetch error: {e}"


def fetch_direct(cfg: dict) -> tuple[list[Posting], list[tuple[str, str]]]:
    cache = detect.load_cache()
    firms = cfg.get("firms") or []
    out: list[Posting] = []
    failures: list[tuple[str, str]] = []
    unsupported: list[str] = []

    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {pool.submit(fetch_one_firm, f, cache): f["name"] for f in firms}
        for fut in as_completed(futs):
            name, postings, err = fut.result()
            if err:
                if "needs implementation" in err or err == "unsupported":
                    unsupported.append(f"{name}\t{err}")
                else:
                    failures.append((name, err))
            out.extend(postings)

    detect.save_cache(cache)
    if unsupported:
        UNSUPPORTED_LOG.write_text("\n".join(sorted(unsupported)) + "\n")
    return out, failures


# ---------- main ----------


def run(*, dry_run: bool, seed: bool) -> int:
    cfg = yaml.safe_load((ROOT / "firms.yaml").read_text())
    rules = FilterRules.from_dict(cfg["filters"])

    log.info("fetching community sources…")
    community = fetch_community(cfg)
    log.info("community: %d raw postings", len(community))

    log.info("fetching direct firms…")
    direct, failures = fetch_direct(cfg)
    log.info("direct: %d raw postings, %d failures", len(direct), len(failures))

    raw = community + direct
    deduped: dict[str, Posting] = {}
    for p in raw:
        # Same firm + external_id may show up via multiple sources; first wins.
        deduped.setdefault(p.key(), p)

    matched = [p for p in deduped.values() if title_passes(p.title, rules)]
    log.info("matched: %d/%d after filter", len(matched), len(deduped))

    previous = load_state()
    is_first_run = not previous

    new_postings, gone, updated_state = diff(matched, previous)
    log.info("diff: new=%d gone=%d", len(new_postings), len(gone))

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook and not dry_run:
        log.error("DISCORD_WEBHOOK_URL is unset — set the secret or use --dry-run")
        return 2

    if seed or is_first_run:
        msg = (
            f"🎯 q27bot initialized — tracking **{len(matched)}** Summer 2027 "
            f"quant intern postings. Future runs will alert on new entries only."
        )
        notify.send_text(webhook, msg, dry_run=dry_run)
    else:
        if new_postings:
            notify.send_postings(webhook, new_postings, dry_run=dry_run)

    if len(failures) > 5:
        msg = f"⚠️ {len(failures)} firms failed this run: " + ", ".join(
            f"{n} ({e[:40]})" for n, e in failures[:8]
        )
        notify.send_text(webhook, msg, dry_run=dry_run)

    if not dry_run:
        save_state(updated_state)

    print(f"summary: matched={len(matched)} new={len(new_postings)} gone={len(gone)} failures={len(failures)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Summer 2027 quant intern monitor")
    parser.add_argument("--dry-run", action="store_true", help="don't post or write state")
    parser.add_argument("--seed", action="store_true", help="seed state, send single summary")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    t0 = time.time()
    rc = run(dry_run=args.dry_run, seed=args.seed)
    log.info("done in %.1fs", time.time() - t0)
    return rc


if __name__ == "__main__":
    sys.exit(main())
