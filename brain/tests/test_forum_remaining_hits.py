"""ssbot.tools.forum_remaining_hits: the hindsight join (forum.md 24.3: avoidable is any analysed tick 4-36 frames
before the contact with a row left clear, not the last one)."""
from ssbot.tools.forum_remaining_hits import hindsight_of


def _ticks(f_c, clear: dict, clear_g: dict | None = None) -> dict:
    """{tick frame: (hs_clear, replay pick's first contact, forced, seen-clear rows, hs_clear_g)} for k frames before."""
    clear_g = clear_g or {}
    return {f_c - k: (n, None, True, 0, clear_g.get(k, 0)) for k, n in clear.items()}


def test_avoid_is_any_tick_in_the_band():
    h = {"f_c": 1000}
    # clear 2 and 9 frames before: the last clear tick is 2 (<= 3), but 9 is in the band
    r = hindsight_of(h, _ticks(1000, {1: 0, 2: 3, 4: 0, 6: 0, 9: 5, 12: 0, 45: 2}))
    assert r["last_clear_k"] == 2 and r["avoid"] and not r["react"]
    # only 1-3 or 45+ frames before: not avoidable
    r = hindsight_of(h, _ticks(1000, {1: 1, 2: 0, 4: 0, 36: 0, 45: 2}))
    assert not r["avoid"] and r["last_clear_k"] == 1
    # the margin variant
    r = hindsight_of(h, _ticks(1000, {4: 2, 6: 1}, {4: 0, 6: 1}))
    assert r["react"] and r["react_g"] and r["avoid_g"]
    r = hindsight_of(h, _ticks(1000, {4: 2}, {4: 0}))
    assert r["avoid"] and not r["avoid_g"]
    assert hindsight_of(h, {}) is None
