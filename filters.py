"""Title-based filter for Summer 2027 quant intern roles.

Rules are loaded from firms.yaml (filters section) so they can be tuned
without touching code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FilterRules:
    must_include_any: tuple[str, ...]
    must_include_role_any: tuple[str, ...]
    must_exclude_any: tuple[str, ...]
    pass_year: str
    reject_years: tuple[str, ...]

    @classmethod
    def from_dict(cls, d: dict) -> "FilterRules":
        return cls(
            must_include_any=tuple(s.lower() for s in d["must_include_any"]),
            must_include_role_any=tuple(s.lower() for s in d["must_include_role_any"]),
            must_exclude_any=tuple(s.lower() for s in d["must_exclude_any"]),
            pass_year=str(d["pass_year"]),
            reject_years=tuple(str(y) for y in d["reject_years"]),
        )


def _word_in(haystack: str, needles: Iterable[str]) -> bool:
    """True if any needle appears as a whole word (case-insensitive)."""
    for n in needles:
        # \b doesn't anchor across non-word characters consistently for multi-word
        # phrases; we keep needles single-token in the config so this is safe.
        if re.search(rf"\b{re.escape(n)}\b", haystack, flags=re.IGNORECASE):
            return True
    return False


def _substring_in(haystack: str, needles: Iterable[str]) -> bool:
    h = haystack.lower()
    return any(n in h for n in needles)


def title_passes(title: str, rules: FilterRules) -> bool:
    """Decide whether a job title qualifies as a Summer 2027 quant intern role.

    The four checks (in order):
      1. includes an "intern" word
      2. includes a quant/research/trading word
      3. doesn't include any excluded substring
      4. year handling: pass on 2027 or no year; reject if 2024/25/26 without 2027
    """
    if not title:
        return False

    lower = title.lower()

    if not _word_in(lower, rules.must_include_any):
        return False
    if not _word_in(lower, rules.must_include_role_any):
        return False
    if _substring_in(lower, rules.must_exclude_any):
        return False

    has_pass_year = rules.pass_year in lower
    if has_pass_year:
        return True
    has_reject_year = any(y in lower for y in rules.reject_years)
    if has_reject_year:
        return False
    # No year mentioned at all → pass (cycle is ambiguous; favor recall).
    return True
