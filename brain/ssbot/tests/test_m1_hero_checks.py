"""Offline checks of the m1_hero probe's HUD cross-checks (they must be able to fail)."""
from ssbot.probes import m1_hero


def mask(n: int, state: str, x0: float, w: float = 40.0, y0: float = 50.0, active: bool = True) -> list:
    return [n, active, state, [x0, y0, x0 + w, y0 + 50.0]]


def test_mask_states_follow_health():
    masks = [mask(1, "Idle", 100), mask(2, "Idle", 150), mask(3, "Empty", 200), mask(4, "Empty", 250, active=False)]
    ok, _ = m1_hero.mask_states_follow_health(masks, health=2, max_health=3)
    assert ok is True
    masks[2][2] = "Idle"  # an empty mask in the full state: the FSM does not follow health
    ok, _ = m1_hero.mask_states_follow_health(masks, health=2, max_health=3)
    assert ok is False
    ok, _ = m1_hero.mask_states_follow_health(masks, health=3, max_health=3)
    assert ok is None  # full health: nothing to compare


def test_mask_row():
    row = [mask(i + 1, "Idle", 100 + 50 * i) for i in range(5)]
    ok, _ = m1_hero.mask_row(row)
    assert ok is True
    row[3][3] = [290.0, 50.0, 330.0, 100.0]  # centre 310 instead of 270: uneven spacing
    ok, detail = m1_hero.mask_row(row)
    assert ok is False and "uneven spacing" in detail
    row = [mask(i + 1, "Idle", 100 + 50 * i) for i in range(5)]
    row[2][3] = [200.0, 120.0, 240.0, 170.0]  # one mask 70 px lower
    ok, detail = m1_hero.mask_row(row)
    assert ok is False and "not one row" in detail
    row = [mask(i + 1, "Idle", 100 + 50 * i, w=40.0 if i != 1 else 20.0) for i in range(5)]
    ok, detail = m1_hero.mask_row(row)
    assert ok is False and "unequal widths" in detail
    ok, _ = m1_hero.mask_row(row[:1])
    assert ok is None


def test_chunks_on_slots():
    slots = [[100.0 + 20 * i, 80.0] for i in range(9)]
    spool = {"slots": slots, "pitch": 20.0, "chunks": [[100.0 + 20 * i + 2, 81.0] for i in range(4)]}
    ok, _ = m1_hero.chunks_on_slots(spool, silk=4)
    assert ok is True
    spool["chunks"][2] = [150.0, 80.0]  # half a pitch off
    ok, _ = m1_hero.chunks_on_slots(spool, silk=4)
    assert ok is False
    ok, _ = m1_hero.chunks_on_slots(spool, silk=3)  # 4 chunks for 3 silk: a regen chunk, not comparable
    assert ok is None
    ok, _ = m1_hero.chunks_on_slots({"slots": slots, "pitch": 20.0, "chunks": []}, silk=0)
    assert ok is None
