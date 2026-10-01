"""hits_to_death (DESIGN §3.7.1) as a table of cases, the support -> Ctx summary, the audit view of the Fractured Mask,
and the batch evaluator against the scalar code."""
import itertools

import numpy as np
import pytest

from ssbot.safety.hits_to_death import (MASK_BROKEN, MASK_INTACT, MASK_NONE, MASK_UNKNOWN, UNBOUNDED, Ctx,
                                        SupportEvent, after_event, ctx_from_support, hits_to_death,
                                        hits_to_death_after, hits_to_death_batch, mask_intact, mask_state)

BELL = Ctx(D1=2)          # Bell Beast: body, leap, bells all 2 masks

CASES = [
    # (name, hp, blue, mask_intact, ctx, expected)
    ("Bell Beast 5 masks", 5, 0, False, BELL, 3),            # 5 -> 3 -> 1 -> dead
    ("Bell Beast 4", 4, 0, False, BELL, 2),
    ("Bell Beast 3", 3, 0, False, BELL, 2),                  # 3 -> 1 -> dead
    ("Bell Beast 2", 2, 0, False, BELL, 1),
    ("Bell Beast 1", 1, 0, False, BELL, 1),
    ("1-mask hits, 5 HP", 5, 0, False, Ctx(D1=1), 5),
    ("lifeblood adds to health", 3, 2, False, BELL, 3),      # h = 5
    ("lifeblood only", 1, 1, False, BELL, 1),
    ("Fractured Mask intact", 5, 0, True, BELL, 4),          # 5 -> 3 -> 1 -> mask: 1 -> dead
    ("Fractured Mask intact at 1 HP", 1, 0, True, BELL, 2),
    ("Fractured Mask intact, uncovered threat", 5, 0, True, Ctx(D1=2, mask_covers=False), 3),
    ("Fractured Mask broken", 5, 0, False, BELL, 3),
    ("critical in support, 5 HP", 5, 0, False, Ctx(D1=1, critical_in_support=True), 2),   # 5 -> 1 -> dead
    ("critical, mask intact", 5, 0, True, Ctx(D1=1, critical_in_support=True), 3),        # 5 -> 1 -> mask -> dead
    ("critical at 1 HP", 1, 0, False, Ctx(D1=1, critical_in_support=True), 1),
    ("critical larger than D1 only above 2 HP", 2, 0, False, Ctx(D1=2, critical_in_support=True), 1),
    ("pending damage lowers h", 5, 0, False, Ctx(D1=2, pending_dmg=1), 2),                # h 4 -> 2 -> dead
    ("pending damage lethal", 2, 0, False, Ctx(D1=1, pending_dmg=2), 0),
    ("pending lethal, mask intact but not covering", 2, 0, True, Ctx(D1=1, pending_dmg=2), 0),
    ("pending lethal, mask covers it", 2, 0, True, Ctx(D1=1, pending_dmg=2, pending_mask_covers=True), 1),
    ("pending lethal through blue too", 1, 1, False, Ctx(D1=1, pending_dmg=3), 0),
    ("nothing can hurt", 5, 0, False, Ctx(D1=0), UNBOUNDED),
    ("critical only, at 1 HP nothing else hurts", 1, 0, False, Ctx(D1=0, critical_in_support=True), UNBOUNDED),
]


@pytest.mark.parametrize("name,hp,blue,mask,ctx,expected", CASES, ids=[c[0] for c in CASES])
def test_table(name, hp, blue, mask, ctx, expected):
    assert hits_to_death(hp, blue, mask, ctx) == expected


def test_fractured_mask_states_from_the_audit():
    assert mask_state({"equipped": True, "amount_left": 1}) == MASK_INTACT
    assert mask_state({"equipped": True, "amount_left": 0}) == MASK_BROKEN
    assert mask_state({"equipped": False, "amount_left": 0}) == MASK_NONE
    assert mask_state({"equipped": None, "amount_left": 1}) == MASK_UNKNOWN     # tools unreadable
    assert mask_state(None) == MASK_UNKNOWN
    # UNKNOWN counts as broken: same h as a broken mask, one less than an intact one
    for st, h in ((MASK_INTACT, 4), (MASK_BROKEN, 3), (MASK_UNKNOWN, 3), (MASK_NONE, 3)):
        assert hits_to_death(5, 0, mask_intact(st), BELL) == h, st


def test_ctx_from_support():
    ctx = ctx_from_support([SupportEvent("Bone Beast", 2), SupportEvent("BoneBeast DropBell L", 1)])
    assert ctx == Ctx(D1=2)
    ctx = ctx_from_support([SupportEvent("Lace", 2, hits=2), SupportEvent("Maul", 1, mask_covers=False)],
                           pending_dmg=1)
    assert (ctx.D1, ctx.mask_covers, ctx.pending_dmg) == (2, False, 1)
    ctx = ctx_from_support([SupportEvent("Judge", critical=True)])
    assert ctx.critical_in_support and ctx.D1 == 0
    assert ctx_from_support([]) == Ctx(D1=0)


def test_after_one_event():
    assert after_event(5, 0, False, BELL) == (3, False)
    assert after_event(1, 0, True, BELL) == (1, False)             # the mask takes it
    assert after_event(1, 0, False, BELL) is None
    assert hits_to_death_after(5, 0, False, BELL, BELL) == 2
    assert hits_to_death_after(5, 0, False, Ctx(D1=4), BELL) == 1    # 5 -> 1 survives; the next 2-mask hit kills
    assert hits_to_death_after(3, 0, False, Ctx(D1=4), BELL) == 0    # the window's event itself kills


def test_batch_matches_scalar():
    grid = list(itertools.product(range(-1, 10), range(0, 3), (False, True), range(0, 4), range(0, 3), (False, True),
                                  (False, True), (False, True)))
    a = np.array(grid, dtype=np.int64).T
    out = hits_to_death_batch(*a, use_numba=False)
    want = [hits_to_death(hp, blue, bool(m), Ctx(D1=d1, pending_dmg=pd, mask_covers=bool(mc),
                                                pending_mask_covers=bool(pmc), critical_in_support=bool(cr)))
            for hp, blue, m, d1, pd, mc, pmc, cr in grid]
    assert out.tolist() == want


def test_batch_broadcasts():
    out = hits_to_death_batch(np.arange(1, 6), 0, False, 2)
    assert out.tolist() == [1, 1, 2, 2, 3]
    out = hits_to_death_batch(np.arange(1, 6)[:, None], 0, np.array([False, True]), 2)
    assert out.shape == (5, 2) and out[4].tolist() == [3, 4]
