from __future__ import annotations

from monitor import diff
from sources.base import Posting


def _p(firm: str, ext: str, title: str = "Quant Intern") -> Posting:
    return Posting(
        firm=firm,
        external_id=ext,
        title=title,
        location="NYC",
        url=f"https://example.com/{firm}/{ext}",
        source="greenhouse",
    )


def test_first_run_all_new() -> None:
    cur = [_p("Citadel", "1"), _p("DRW", "2")]
    new, gone, state = diff(cur, {})
    assert len(new) == 2
    assert gone == []
    assert set(state) == {"Citadel::1", "DRW::2"}
    for v in state.values():
        assert "first_seen" in v and "last_seen" in v


def test_idempotent_run_yields_no_new() -> None:
    """Two runs over the same upstream snapshot must produce zero notifications."""
    cur = [_p("Citadel", "1"), _p("DRW", "2")]
    _, _, state1 = diff(cur, {})
    new2, gone2, state2 = diff(cur, state1)
    assert new2 == []
    assert gone2 == []
    # last_seen advances; first_seen stays.
    for k in state1:
        assert state1[k]["first_seen"] == state2[k]["first_seen"]


def test_gone_kept_in_state_with_last_seen() -> None:
    """Postings that disappear are retained in state — never deleted."""
    cur1 = [_p("Citadel", "1"), _p("DRW", "2")]
    _, _, state1 = diff(cur1, {})
    cur2 = [_p("Citadel", "1")]  # DRW disappears
    new, gone, state2 = diff(cur2, state1)
    assert new == []
    assert gone == ["DRW::2"]
    assert "DRW::2" in state2  # not deleted


def test_new_posting_detected() -> None:
    cur1 = [_p("Citadel", "1")]
    _, _, state1 = diff(cur1, {})
    cur2 = [_p("Citadel", "1"), _p("Jane Street", "9", title="Quant Trader Intern")]
    new, gone, _ = diff(cur2, state1)
    assert len(new) == 1
    assert new[0].firm == "Jane Street"
    assert gone == []
