"""Task 1v1 SG5 (SSBOT_FORUM_CHASE, forum.md 61): the switch is off by default and needs the slam map; the chase rows
(toward the Clapper, a slash every 19 frames, the side key held after each press, only while it idles / walks / evades /
enters, not after a jump cast); the L2 chase stance (the readiness argmax in the band, else 4 u; its stance weight x2;
the slam / jump / rune / cast branches unchanged); the readiness while it evades (After Scuttle branches at once) and
the readiness tier (near rows below R_ref after the others)."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_planner as fp
from ssbot.knowledge import kinematics as kin
from tests.test_forum_l2 import CC, WinFc, clapper, l2, subj, world
from tests.test_special_map_sg4 import _helper, _mock, setup  # noqa: F401 (the module fixture)


def test_switch_is_off_by_default_and_needs_the_map(monkeypatch):
    from ssbot.combat.tactics import gauntlet
    monkeypatch.delenv("SSBOT_FORUM_CHASE", raising=False)
    monkeypatch.setenv("SSBOT_FORUM_SPECIAL_MAP", "1")
    assert not gauntlet._chase_on()
    monkeypatch.setenv("SSBOT_FORUM_CHASE", "1")
    monkeypatch.setenv("SSBOT_FORUM_SPECIAL_MAP", "0")
    assert not gauntlet._chase_on()
    monkeypatch.setenv("SSBOT_FORUM_SPECIAL_MAP", "1")
    assert gauntlet._chase_on()
    import os
    if os.environ.get("SSBOT_FORUM_CHASE") is None:     # (the module constant read at import)
        assert not fp.CHASE


class _Map:
    def __init__(self, cx, fam=None, d=None):
        self.e = {"type_key": CC, "pos": [cx, 7.45]}
        self.inst = None if fam is None else NS(fam=fam)
        self.d = d

    def _clapper(self, f, hx):
        d = abs(self.e["pos"][0] - hx) if self.d is None else self.d
        return (d, 7, CC, self.e, self.inst)


def _chase(mp, hx=20.0, T=36, t=10.0, jc=None):
    pl = NS(_map=mp, _chase_jc={} if jc is None else jc)
    st = np.zeros((kin.K, 1))
    st[kin.PX, 0] = hx
    f = NS(rs=NS(trk=NS(T=t)))
    return fp.ForumPlanner._chase_rows(pl, f, st, T), pl


def test_chase_rows_masks():
    (cmd, names, bits), _ = _chase(_Map(28.0))
    # 8 u: a run reaches 4.3 u at frame ~27: presses at 20 / 24 (within 8 frames), and the dash rows (beyond 6.5 u)
    assert sorted({n.split("_f")[0] for n in names}) == sorted(
        ["CHASE run20", "CHASE run24"] + [f"CHASE dash{k}" for k in fp.CHASE_DASH_K])
    assert len(cmd) == len(names) == len(bits) == 2 * (2 + len(fp.CHASE_DASH_K))
    (_, near, _), _ = _chase(_Map(24.5))                        # 4.5 u: presses at 0 / 4 / 8, no dash
    assert sorted({n.split("_f")[0] for n in near}) == ["CHASE run0", "CHASE run4", "CHASE run8"]
    toward = kin.B_RIGHT                                          # the Clapper at 28, the hero at 20
    for m, nm in zip(cmd, names):
        k1 = int(nm.split()[1][4 if nm.split()[1].startswith("dash") else 3:].split("_")[0])
        fol = int(nm.split("_f")[1])
        press = np.flatnonzero((m & kin.B_ATTACK) != 0)
        want = sorted({k + j for k in range(k1, 36, fp.CHASE_PERIOD) for j in range(3) if k + j < 36})
        assert press.tolist() == want, nm
        assert not (m & kin.B_LEFT).any()                         # never away
        assert ((m[:k1] & toward) != 0).all()                     # run until the first press
        for k in range(k1, 36, fp.CHASE_PERIOD):
            assert ((m[k:k + fol] & toward) != 0).all()          # the knockback followed
            assert not (m[k + fol:min(36, k + fp.CHASE_PERIOD)] & toward).any() or k + fol >= 36
        if nm.startswith("CHASE dash"):
            assert ((m[:3] & kin.B_DASH) != 0).all() and not (m[3:] & kin.B_DASH).any() and k1 >= 10
        else:
            assert not (m & kin.B_DASH).any()
    (cmd2, _, _), _ = _chase(_Map(12.0))
    assert not (cmd2 & kin.B_RIGHT).any() and (cmd2 & kin.B_LEFT).any()


def test_chase_rows_only_outside_its_moves():
    for fam in ("CC_SLAM", "CC_CAST", "CC_JUMP"):
        assert _chase(_Map(28.0, fam))[0] is None
    for fam in (None, "CC_EVADE", "CC_ENTRY"):
        assert _chase(_Map(28.0, fam))[0] is not None
    assert _chase(_Map(28.0, d=14.5))[0] is None                  # too far
    assert _chase(_Map(20.2))[0] is None                          # on top of it
    # a jump cast: its rune circle bursts after the move: no chase rows for CHASE_RUNE_S
    r, pl = _chase(_Map(28.0, "CC_JUMP_CAST"), t=10.0)
    assert r is None and pl._chase_jc[7] == 10.0
    assert _chase(_Map(28.0), t=10.0 + fp.CHASE_RUNE_S - 0.05, jc=pl._chase_jc)[0] is None
    assert _chase(_Map(28.0), t=10.0 + fp.CHASE_RUNE_S + 0.05, jc=pl._chase_jc)[0] is not None
    assert fp.ForumPlanner._chase_rows(NS(_map=None, _chase_jc={}), None, np.zeros((kin.K, 1)), 36) is None


def test_tier_low_rows():
    R = np.array([3.2, 2.5, 2.5, -np.inf, np.nan, 1.0])
    safe = np.array([True, True, True, True, True, False])
    xe = np.array([34.0, 34.0, 38.0, 32.5, 34.0, 34.0])           # the Clapper at 30
    low = fp.chase_tier_low(R, safe, xe, 30.0, 3.0)
    # 4 u with 3.2: kept; 4 u with 2.5: low; 8 u with 2.5: beyond the near band (the soft penalty only); -inf near:
    # low; nan (not computed): never; unsafe: never
    assert low.tolist() == [False, True, False, True, False, False]
    assert not fp.chase_tier_low(R, safe, xe, None, 3.0).any()


def test_l2_chase_stance(monkeypatch):
    from ssbot.combat import forum_map
    from ssbot.combat.tactics import gauntlet
    monkeypatch.setenv("SSBOT_FORUM_SPECIAL_MAP", "1")
    monkeypatch.delenv("SSBOT_FORUM_CHASE", raising=False)
    forum_map.BOARD.clear()
    s = [subj(9, CC, 30.0, y=7.45)]
    t = l2()
    p0 = t.decide(world(20.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert p0.stance_x == pytest.approx(26.0) and t.last["goal_why"].endswith("face")
    monkeypatch.setenv("SSBOT_FORUM_CHASE", "1")
    t = l2()
    p = t.decide(world(20.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert t.last["goal_why"].endswith("chase") and p.stance_x == pytest.approx(30.0 - gauntlet.CHASE_U)
    assert p.weights["stance"] == pytest.approx(p0.weights["stance"] * gauntlet.CHASE_STANCE_X)
    assert p.hit_w[9] == pytest.approx(3.0)
    # the map's readiness argmax inside the band (BOARD, the planner's last tick)
    forum_map.BOARD[9] = {"on": False, "x": None, "ready_x": 24.5, "chase_x": 25.8}
    t = l2()
    p = t.decide(world(20.0, ents=[clapper(9, 30.0, False)]), WinFc(s), None, 3)
    assert t.last["goal_why"].endswith("chase: ready") and p.stance_x == pytest.approx(25.8)
    # the evade: chase at once (its stance follows it)
    s2 = [subj(9, CC, 33.0, y=7.45, state="Evade Scuttle", family="CC_EVADE", committed=True)]
    forum_map.BOARD.clear()
    t = l2()
    p = t.decide(world(27.0, ents=[clapper(9, 33.0, False)]), WinFc(s2), None, 3)
    assert t.last["goal_why"].endswith("chase") and p.stance_x == pytest.approx(29.0)
    # unchanged: the slam (step out, no map row here), the cast (rune face / face), the jump
    s3 = [subj(9, CC, 35.0, y=7.45, state="Slam Antic", family="CC_SLAM", committed=True)]
    t = l2()
    p = t.decide(world(30.0, ents=[clapper(9, 35.0, False)]), WinFc(s3), None, 3)
    assert p.stance_x == pytest.approx(22.0) and p.hit_w.get(9, 0.0) == 0.0
    s4 = [subj(9, CC, 30.0, y=7.45, state="Spell Antic", family="CC_CAST", committed=True)]
    t = l2()
    p = t.decide(world(24.0, ents=[clapper(9, 30.0, False)]), WinFc(s4), None, 3)
    assert not t.last["goal_why"].endswith("chase")
    s5 = [subj(9, CC, 35.0, y=7.45, state="Jump Antic", family="CC_JUMP", committed=True)]
    t = l2()
    t.decide(world(26.0, ents=[clapper(9, 35.0, False)]), WinFc(s5), None, 3)
    assert "jump:" in t.last["goal_why"]
    forum_map.BOARD.clear()


def test_readiness_while_it_evades_and_the_chase_spot(setup, monkeypatch):  # noqa: F811
    from ssbot.combat import forum_map
    from ssbot.combat import special_map_rt as rt
    from ssbot.combat.hero_macros import ALPHAS
    h, R = _helper(setup)
    params = setup["params"]
    cx = 40.0
    T = 36
    xs = np.array([cx + 4.5, cx + 7.0])
    box = np.zeros((2, T + 1, 4))
    y0 = setup["hm"].stand_y0
    for i, x in enumerate(xs):
        box[i, :, 0], box[i, :, 2] = x - 0.25, x + 0.25
        box[i, :, 1], box[i, :, 3] = y0, y0 + 1.3
    r1 = NS(box=box, flags=np.full((2, T + 1), kin.F_GROUND, np.int64), mode=np.zeros((2, T + 1), np.int64))
    cmd = np.zeros((2, T), np.int64)
    start = kin.initial_state(params, cx + 4.0, setup["hm"].stand_py, facing=-1, ground=True, alpha=ALPHAS[0])
    f, e = _mock(cx, "Evade Scuttle", 0.1)
    e["vel"] = [-6.0, 0.0]                                        # scuttling away from the hero (+x)
    monkeypatch.setattr(forum_map, "CHASE", False)
    assert h.readiness(f, start, r1, cmd, 0, 0) is None           # SG4: decision states only
    monkeypatch.setattr(forum_map, "CHASE", True)
    out = h.readiness(f, start, r1, cmd, 0, 1)
    assert out is not None
    assert h.ready_cx == pytest.approx(cx - 6.0 * (forum_map.EVADE_S - 0.1))     # where the scuttle ends
    b = forum_map.BOARD[7]
    lo, hi = forum_map.CHASE_BAND
    assert lo - 1e-6 <= b["chase_x"] - h.ready_cx <= hi + 1e-6 and b["R_ref"] == pytest.approx(R.ready_ref)
    # a decision state: no carry, the chase spot in the band
    f2, _ = _mock(cx, "Walk", 0.3)
    assert h.readiness(f2, start, r1, cmd, 0, 2) is not None and h.ready_cx == pytest.approx(cx)
    assert lo - 1e-6 <= forum_map.BOARD[7]["chase_x"] - cx <= hi + 1e-6
    assert rt.READY_RANGE_U > hi


def test_readiness_of_a_row_ending_in_a_swing(setup, monkeypatch):  # noqa: F811
    """CHASE: a ground row ending mid-swing meets a slam starting then only when the swing ends: the map's value k_lock
    = attack_duration - the swing's frames so far into the antic (never above the free hero's)."""
    from ssbot.combat import forum_map
    from ssbot.combat.hero_macros import ALPHAS
    h, R = _helper(setup)
    params = setup["params"]
    cx, T = 40.0, 36
    xs = np.array([cx + 4.5, cx + 4.5, cx + 6.0])
    box = np.zeros((3, T + 1, 4))
    y0 = setup["hm"].stand_y0
    for i, x in enumerate(xs):
        box[i, :, 0], box[i, :, 2] = x - 0.25, x + 0.25
        box[i, :, 1], box[i, :, 3] = y0, y0 + 1.3
    flags = np.full((3, T + 1), kin.F_GROUND, np.int64)
    flags[1, -4:] |= kin.F_ATTACKING                              # 4 frames into a swing at the end
    flags[2, -1:] |= kin.F_ATTACKING
    r1 = NS(box=box, flags=flags, mode=np.zeros((3, T + 1), np.int64))
    cmd = np.zeros((3, T), np.int64)
    start = kin.initial_state(params, cx + 4.0, setup["hm"].stand_py, facing=-1, ground=True, alpha=ALPHAS[0])
    f, _ = _mock(cx, "Idle", 0.3)
    monkeypatch.setattr(forum_map, "CHASE", False)
    _, R0 = h.readiness(f, start, r1, cmd, 0, 0)
    assert R0[0] == R0[1]                                         # SG4: the swing is not looked at
    monkeypatch.setattr(forum_map, "CHASE", True)
    _, R1 = h.readiness(f, start, r1, cmd, 0, 1)
    att_f = int(round(params.attack_duration * 60))
    from ssbot.combat import special_map_rt as rt
    S0 = np.asarray(start).reshape(kin.K, -1)[:, 0]
    p_end = sorted({(q - T) % 6 for q in rt.phases_of(float(S0[kin.ALO]), float(S0[kin.AHI]), 0)} & set(R.srcs))
    for i, n in ((1, 4), (2, 1)):
        v = min(R.srcs[p].S(att_f - n, 0, float(xs[i] - cx), 0) for p in p_end)
        assert R1[i] <= R0[i] + 1e-9 and R1[i] == pytest.approx(min(R0[i], v))
    assert R1[0] == R0[0] and h.swing_rows == 2
