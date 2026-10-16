"""Task 1v1 SG5 review (forum.md 61.x): the chase (SSBOT_FORUM_CHASE) only where the slam map handles a slam that
starts now: no chase without the map; none where the map leaves the slam to the full checks because of a wall (its wall
exit for the Clapper facing the hero); while the Clapper evades, the readiness is read at the evade's end (After Scuttle
branches at once: the slam starts there, not at the row's end); a jump cast is noted at any distance and in any mode."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_planner as fp
from ssbot.knowledge import kinematics as kin
from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world
from tests.test_special_map_sg4 import _helper, _mock, setup  # noqa: F401 (the module fixture)


def _idle(cx: float, state: str = "Idle", t: float = 0.5, fam=None, t_trk: float = 10.0, vel=(0.0, 0.0)):
    e = {"type_key": "Song Heavy Sentry", "pos": [cx, 7.45], "flipX": True, "vel": list(vel),
         "fsms": [{"name": "Control", "state": state, "t": t}]}
    inst = None if fam is None else NS(fam=fam, t0=1.0, x0=None)
    trk = NS(now={7: ("Song Heavy Sentry", e, inst)}, T=t_trk)
    return NS(rs=NS(trk=trk, k_shift=0)), e


def _rows(helper, f, hx, T=36, jc=None):
    pl = NS(_map=helper, _chase_jc={} if jc is None else jc)
    st = np.zeros((kin.K, 1))
    st[kin.PX, 0] = hx
    return fp.ForumPlanner._chase_rows(pl, f, st, T), pl


def test_no_chase_without_the_map(monkeypatch):
    """The map file missing (special_map_rt.runtime None): the planner runs without the map, so no chase rows and no
    L2 chase stance (the slam is not handled)."""
    from ssbot.combat import forum_map
    from ssbot.combat.tactics import gauntlet
    pl = NS(params=None, terrain=kin.Terrain2D.from_boxes([(0.0, 0.0, 80.0, 1.0)]))
    h = forum_map.MapHelper(pl)
    h._loaded, h._rt = True, None                                 # loaded, no map file
    f, _ = _idle(30.0)
    assert _rows(h, f, 24.0)[0] is None
    monkeypatch.setenv("SSBOT_FORUM_SPECIAL_MAP", "1")
    monkeypatch.setenv("SSBOT_FORUM_CHASE", "1")
    monkeypatch.setitem(forum_map.MAP_READY, "ok", False)
    forum_map.BOARD.clear()
    s = [subj(9, CC, 30.0, y=7.45)]
    t = l2()
    t.decide(world(20.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert not t.last["goal_why"].endswith("chase")
    monkeypatch.setitem(forum_map.MAP_READY, "ok", True)
    t = l2()
    t.decide(world(20.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert t.last["goal_why"].endswith("chase")


def test_no_chase_where_the_map_has_no_slam_row(setup, monkeypatch):  # noqa: F811
    """A Clapper 3.5 u from the left wall facing the hero 4 u to its right: a slam starting there gets no map row (the
    wall exit: 6 u behind the anchor), so the readiness there is not backed by the map: no chase rows, no chase spot,
    no tier (rnmap's readiness penalty and its 'face: ready' stay)."""
    from ssbot.combat import forum_map
    from ssbot.combat.hero_macros import ALPHAS
    h, R = _helper(setup)
    params = setup["params"]
    monkeypatch.setattr(forum_map, "CHASE", True)
    lo = forum_map.FORUM_ARENA[0]
    cx, hx = lo + 3.5, lo + 7.5
    # the map leaves this slam (the map row's wall exit)
    fa, _ = _mock(cx, "Slam Antic", 0.1)
    st_a = kin.initial_state(params, hx, setup["hm"].stand_py, facing=-1, ground=True, alpha=ALPHAS[0])
    assert h.row(fa, st_a, kin.HoldState.idle(), np.zeros(0, np.int64), 36, 0) is None and h.info["why"] == "wall"
    T = 36
    y0 = setup["hm"].stand_y0
    box = np.zeros((1, T + 1, 4))
    box[0, :, 0], box[0, :, 2], box[0, :, 1], box[0, :, 3] = hx - 0.25, hx + 0.25, y0, y0 + 1.3
    r1 = NS(box=box, flags=np.full((1, T + 1), kin.F_GROUND, np.int64), mode=np.zeros((1, T + 1), np.int64))
    cmd = np.zeros((1, T), np.int64)
    f, _ = _idle(cx)
    forum_map.BOARD.clear()
    out = h.readiness(f, st_a, r1, cmd, 0, 1)
    assert out is not None                                        # SG4's penalty as in rnmap
    b = forum_map.BOARD[7]
    assert b.get("chase_x") is None and b.get("chase_off") == "wall" and b.get("ready_x") is not None
    assert h.ready_cx is None                                     # no readiness tier
    assert _rows(h, f, hx)[0] is None                             # no chase rows
    # L2: the planner's gate (BOARD) -> SG4's "face: ready"; without BOARD its own wall check
    monkeypatch.setenv("SSBOT_FORUM_SPECIAL_MAP", "1")
    monkeypatch.setenv("SSBOT_FORUM_CHASE", "1")
    monkeypatch.setitem(forum_map.MAP_READY, "ok", True)
    s = [subj(9, CC, cx, y=7.45)]
    forum_map.BOARD[9] = dict(b)
    t = l2()
    t.decide(world(hx, ents=[clapper(9, cx, True)]), WinFc(s), None, 3)
    assert t.last["goal_why"].endswith("face: ready")
    forum_map.BOARD.clear()
    t = l2()
    t.decide(world(hx, ents=[clapper(9, cx, True)]), WinFc(s), None, 3)
    assert not t.last["goal_why"].endswith("chase")
    # in the open: chase as before
    cx2, hx2 = 32.0, 36.0
    f2, _ = _idle(cx2)
    box2 = box.copy()
    box2[..., 0] += hx2 - hx
    box2[..., 2] += hx2 - hx
    st_b = kin.initial_state(params, hx2, setup["hm"].stand_py, facing=-1, ground=True, alpha=ALPHAS[0])
    assert h.readiness(f2, st_b, NS(box=box2, flags=r1.flags, mode=r1.mode), cmd, 0, 2) is not None
    assert forum_map.BOARD[7].get("chase_x") is not None and h.ready_cx == pytest.approx(cx2)
    assert _rows(h, f2, hx2)[0] is not None
    forum_map.BOARD.clear()


def test_evade_readiness_at_its_end(setup, monkeypatch):  # noqa: F811
    """While it evades, a slam starts when the scuttle ends (After Scuttle branches at once): the readiness is the
    map's at the row's state then, not at the row's end. Row 0 is close when the scuttle ends and back at 4.5 u at its
    end; row 1 stays at 4.5 u."""
    from ssbot.combat import forum_map
    from ssbot.combat import special_map_rt as rt
    from ssbot.combat.hero_macros import ALPHAS
    h, R = _helper(setup)
    params = setup["params"]
    monkeypatch.setattr(forum_map, "CHASE", True)
    cx, T, P = 32.0, 36, 6
    start = kin.initial_state(params, cx + 4.5, setup["hm"].stand_py, facing=-1, ground=True, alpha=ALPHAS[0])
    S0 = np.asarray(start).reshape(kin.K, -1)[:, 0]
    q0 = rt.phases_of(float(S0[kin.ALO]), float(S0[kin.AHI]), 0)
    t_in = 0.15
    k_ev = int(round((forum_map.EVADE_S - t_in) * 60))            # 12 frames (the setup's map has 2 of the 6 phases:
    pe = sorted({(q - k_ev) % 6 for q in q0} & set(R.srcs))       # P + T - k_ev = 30, a multiple of 6)
    assert pe

    def val(x):
        return float(min(R.readiness_rows(p, np.array([x]), np.array([0]), np.array([True]), np.zeros(1),
                                          np.zeros(1))[0] for p in pe))
    xs = [1.0, 1.5, 2.0, 2.5, 3.0]
    xa = min(xs, key=val)
    assert val(xa) < val(4.5) - 0.5                               # (the setup's map: closer is worse)
    y0 = setup["hm"].stand_y0

    def rows(P_):
        box = np.zeros((2, P_ + T + 1, 4))
        path = np.full((2, P_ + T + 1), cx + 4.5)
        path[0, k_ev - 3:k_ev + 4] = cx + xa
        box[..., 0], box[..., 2] = path - 0.25, path + 0.25
        box[..., 1], box[..., 3] = y0, y0 + 1.3
        return NS(box=box, flags=np.full((2, P_ + T + 1), kin.F_GROUND, np.int64),
                  mode=np.zeros((2, P_ + T + 1), np.int64))
    cmd = np.zeros((2, T), np.int64)
    f, _ = _idle(cx, "Evade Scuttle", t_in)                       # no velocity: the end where it is now
    out = h.readiness(f, start, rows(P), cmd, P, 0)
    assert out is not None
    _, Rr = out
    assert Rr[0] == pytest.approx(val(xa)) and Rr[0] < Rr[1] - 0.5
    assert Rr[1] == pytest.approx(val(4.5))
    assert h.ready_j == k_ev
    # the evade over before the prefix ends: the first frame after it (P = 5: index 6); a decision state: the row's
    # end as before (P = 6: index 42, a multiple of 6)
    f2, _ = _idle(cx, "Evade Scuttle", forum_map.EVADE_S)
    assert h.readiness(f2, start, rows(5), cmd, 5, 1) is not None and h.ready_j == 6
    f3, _ = _idle(cx, "Idle", 0.5)
    _, R3 = h.readiness(f3, start, rows(P), cmd, P, 2)
    assert h.ready_j == P + T and R3[0] == pytest.approx(R3[1])


def test_jump_cast_noted_at_any_distance():
    """CHASE_RUNE_S counts from the last tick of the jump cast wherever the hero is (beyond NEAR_U, in a dash, on a
    wall: _chase_rows is not reached then); _chase_rows only reads it."""
    pl = NS(_chase_jc={})
    f, _ = _idle(60.0, "Slam 2", fam="CC_JUMP_CAST", t_trk=10.0)  # 20+ u away
    fp.ForumPlanner._chase_note_jc(pl, f)
    assert pl._chase_jc.get(7) == 10.0

    class _H:
        def __init__(self, cx):
            self.e = {"type_key": CC, "pos": [cx, 7.45], "fsms": [{"name": "Control", "state": "Idle", "t": 0.3}]}

        def _clapper(self, f, hx):
            return (abs(self.e["pos"][0] - hx), 7, CC, self.e, None)

        def clapper_x(self, e, stt):
            return float(e["pos"][0]), None

        def chase_gate(self, cx, hx):
            return None
    for dt, want in ((0.5, None), (fp.CHASE_RUNE_S + 0.05, "rows")):
        f2 = NS(rs=NS(trk=NS(now={}, T=10.0 + dt)))
        pl2 = NS(_map=_H(30.0), _chase_jc=pl._chase_jc)
        st = np.zeros((kin.K, 1))
        st[kin.PX, 0] = 22.0
        r = fp.ForumPlanner._chase_rows(pl2, f2, st, 36)
        assert (r is None) == (want is None), dt
