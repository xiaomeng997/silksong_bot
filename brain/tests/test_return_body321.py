"""Task 179 #321 (Sol seq 245): SSBOT_FORUM_TWO_RETURN_BODY's narrowed body in stack_ret is the body joined with its
known standing poses in both facings - RangeTracker.standing_body, attack_range._jb_turn_mask at the root carried as
estimate() carries the body (IDLE_CARRY, carry_shift's wall clip). Recorded case (w13_observe_bait, Clapper 335476):
standing Idle facing right (flipX: its longer front half at +x) at 2835 with a hero descending beside its back, at
2836 it turned to face her (Walk, backing off to the right) and its body changed with the turn, not a pure mirror -
the near (left) edge 0.705 u closer, the top 6.92 -> 6.19 and back to 6.92 at 2841 - so the #315 narrowed body (that
body + FOCUS_M) admitted her landing beside its back side, which the turned body met. Outside the shape's domain nothing is
narrowed (the original layer). A shape bound only: not a forecast of its walk or a reversal."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.combat import forum_v2 as v2
from ssbot.combat import jump_behind as jb
from ssbot.core.forum import WALL_L

CL = jb.CLAPPER
ROOT, ROOT_Y = 20.412172317504883, 7.449374198913574
IDLE_R = (19.07154655456543, 3.0149991512298584, 22.663734436035156, 6.916561603546143)   # 2835 Idle, facing right
WALK_L = (18.366859436035156, 3.0149991512298584, 21.752798080444336, 6.1946868896484375)  # 2836 Walk, facing left
# 2841 Walk facing left (its root 21.0522 then; the same shape placed at ROOT): front 2.2516, back 1.3406, top 6.9166
WALK_L_TALL = (ROOT - 2.2516, 3.0149991512298584, ROOT + 1.3406, 6.916561603546143)
FOCUS_BOX = (25.6, 3.015, 29.2, 6.917)                                                     # the other Clapper (focus)


def _box(b):
    x0, y0, x1, y1 = b
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float)


def _mirror(b):
    return (2 * ROOT - b[2], b[1], 2 * ROOT - b[0], b[3])


def _entity(box, x, vel=(0.0, 0.0), state="Idle"):
    return {"pos": [x, ROOT_Y, 0.0], "vel": list(vel), "fsms": [{"state": state, "t": 0.0}],
            "colliders": [{"name": "Song Heavy Sentry (2)", "enabled": True, "damage": {"dealt": 2},
                           "verts_world": _box(box).reshape(-1).tolist()}]}


def _tracker(monkeypatch, box=IDLE_R, vel=(0.0, 0.0), inst=None, state="Idle", focus=False):
    monkeypatch.setattr(ar, "hazards_at", lambda *a, **k: ar.empty_mask())
    monkeypatch.setattr(ar, "type_extra", lambda spec: None)
    monkeypatch.setattr(ar, "COMMIT_CORE", True)
    tab = ar.RangeTable(spec=ar.SPECS[CL], templates={}, meta={})
    trk = ar.RangeTracker(tables={CL: tab})
    trk.now = {476: (CL, _entity(box, ROOT, vel, state), inst)}
    if focus:
        trk.now[470] = (CL, _entity(FOCUS_BOX, 27.4, state="Walk"), None)
    return trk


def _covers(mask, box):
    want = ar.poly_mask([_box(box)])
    return bool(np.all(ar.on_canvas(mask, want.ix0, want.iy0, want.m.shape)[want.m]))


@pytest.mark.parametrize("k", [0, 12, 36, 62])
def test_standing_body_covers_the_recorded_turn_and_walk_cycle_in_both_facings(monkeypatch, k):
    sb = _tracker(monkeypatch).standing_body(476, k)
    assert sb is not None and ar.same_mask(sb, ar._jb_turn_mask(ROOT))      # at rest: no carry
    for b in (IDLE_R, _mirror(IDLE_R), WALK_L, _mirror(WALK_L), WALK_L_TALL, _mirror(WALK_L_TALL)):
        assert _covers(sb, b)
    # the #315 narrowed body was the Idle box alone: it misses the turned body's near edge
    assert not _covers(ar.poly_mask([_box(IDLE_R)]), WALK_L)


def test_standing_body_follows_the_carried_root_and_its_wall_clip(monkeypatch):
    for vx, k in ((8.0, 30), (-8.0, 60), (-8.0, 200)):
        trk = _tracker(monkeypatch, WALK_L, vel=(vx, 0.0), state="Walk")
        dx = ar.carry_shift([_box(WALK_L)], (vx, 0.0), k * ar.FT)[0]
        assert ar.same_mask(trk.standing_body(476, k), ar._jb_turn_mask(ROOT + dx))
    # walking left for 200 frames would cross the wall: the root stops where the body meets it (estimate's own clip)
    assert ar.carry_shift([_box(WALK_L)], (-8.0, 0.0), 200 * ar.FT)[0] == pytest.approx(WALL_L - WALK_L[0])


@pytest.mark.parametrize("box, inst", [
    ((ROOT - 2.4, 3.015, ROOT + 1.34, 6.9), None),           # wider than the standing box
    ((ROOT - 1.34, 3.015, ROOT + 2.25, 7.5), None),           # taller: not a standing pose
    ((ROOT - 1.34, 2.5, ROOT + 2.25, 6.9), None),             # below the floor
    (IDLE_R, NS(fam="CC_SLAM", states=["Slam Antic"])),       # in a move instance
])
def test_outside_the_shape_domain_there_is_no_standing_body(monkeypatch, box, inst):
    assert _tracker(monkeypatch, box, inst=inst).standing_body(476, 36) is None


def test_no_standing_body_for_an_untracked_unit(monkeypatch):
    assert _tracker(monkeypatch).standing_body(999, 0) is None


def test_stack_ret_draws_the_body_and_its_standing_poses_and_the_stack_is_unchanged(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    trk = _tracker(monkeypatch, focus=True)
    off = v2.RangeSupport.build(trk, margin_mode="focus", focus=470)
    rs = v2.RangeSupport.build(trk, margin_mode="focus", focus=470, body2=476)
    assert rs.body2 == 476 and rs.stack_ret is not None and rs.ret_tags
    assert np.array_equal(rs.stack, off.stack) and np.array_equal(rs.stack_esc, off.stack_esc)
    # the #315 narrowing for comparison: the body alone with FOCUS_M (standing_body = the body itself)
    monkeypatch.setattr(trk, "standing_body", lambda iid, k: trk.estimate(iid, k).core, raising=False)
    old = v2.RangeSupport.build(trk, margin_mode="focus", focus=470, body2=476)
    for si, k in enumerate(rs.samples):
        if k <= 12:                      # the rule margin is FOCUS_M there: nothing narrowed, the original layer
            assert np.array_equal(rs.stack_ret[si], rs.stack[si])
            continue
        assert rs.stack_ret[si].sum() > old.stack_ret[si].sum()
        if k >= 22:                      # rule margin >= 1.78 u: the standing poses + FOCUS_M lie inside the stack
            assert np.array_equal(rs.stack_ret[si] | rs.stack[si], rs.stack[si])
        # (k 15 / 18: the rule margin 0.99 / 1.29 u is less than the back edge's 0.91 u turn + FOCUS_M - there the
        # narrowed body reaches a little past the stack on its back side: stricter than the stack, by the turn)
    k = 36
    tk = np.array([k * v2.FT])
    # the late N route's landing beside its back side (hero centre 18.134, 4.054 at k 13-36): the original layer and
    # the new narrowed body hold it, the #315 one did not
    side = (np.array([[18.134]]), np.array([[4.054]]))
    assert rs.occupied(*side, tk)[0, 0] and rs.occupied_ret(*side, tk)[0, 0]
    assert not old.occupied_ret(*side, tk)[0, 0]
    # the on-time route over its top (2823: 20.844, 9.792 at k 19) stays outside the narrowed body
    top = (np.array([[20.844]]), np.array([[9.792]]))
    assert rs.occupied(*top, np.array([19 * v2.FT]))[0, 0]
    assert not rs.occupied_ret(*top, np.array([19 * v2.FT]))[0, 0]


def test_unknown_shape_domain_keeps_the_original_layer(monkeypatch):
    monkeypatch.setattr(v2, "RETURN_BODY", True)
    trk = _tracker(monkeypatch, (ROOT - 2.4, 3.015, ROOT + 1.34, 6.9), focus=True)
    rs = v2.RangeSupport.build(trk, margin_mode="focus", focus=470, body2=476)
    assert rs.body2 == 476 and not rs.ret_tags and rs.stack_ret is None    # the planner reads the stack
