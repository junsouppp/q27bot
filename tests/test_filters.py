from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from filters import FilterRules, title_passes


@pytest.fixture(scope="module")
def rules() -> FilterRules:
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "firms.yaml").read_text())
    return FilterRules.from_dict(cfg["filters"])


@pytest.mark.parametrize(
    "title",
    [
        "Quantitative Trader Intern - Summer 2027",
        "Quant Research Intern",
        "Quantitative Researcher Intern, Summer 2027",
        "Algorithmic Trading Intern",
        "Systematic Research Internship",
        "Trading Intern - 2027",
        # Year present alongside reject year — 2027 still wins.
        "Quant Trading Intern (2026/2027 Cycle)",
    ],
)
def test_pass(rules: FilterRules, title: str) -> None:
    assert title_passes(title, rules), title


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer Intern",
        "SWE Intern - Trading Tech",  # excluded substring wins
        "Marketing Intern - Summer 2027",
        "Quant Trader Intern - Summer 2025",  # reject year, no 2027
        "Quantitative Research Intern - Summer 2026",
        "HR Intern",
        "Data Engineer Intern - Quant Team",  # excluded
        "Compliance Intern",
        "Quant Researcher",  # no "intern" word
        "Senior Quant Trader",  # no intern
        "Graphic Design Intern",
        "",
    ],
)
def test_reject(rules: FilterRules, title: str) -> None:
    assert not title_passes(title, rules), title


def test_no_year_passes(rules: FilterRules) -> None:
    """Spec: titles with no year mentioned at all should pass."""
    assert title_passes("Quant Trader Intern", rules)
    assert title_passes("Quantitative Research Intern", rules)
