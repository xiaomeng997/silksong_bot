"""Map v2 stage M4 S1b: the two verifiers' findings on S1 (HANDOFF 'Task map2 - stage M4' / 'S1b', forum.md 101) - the
downspike lock credited by the bounce's cause, the down slash contact's slack, the side rule out of the air sprint
(the highest body top, the sprint's x lag, the extra velocity's residue), the air sprint's last frame (HERO2
H2_SPR_FIN), the late check from the commit's own state (its press scan after it, the Cogfly keys stripped) and the
bot side's warm-up of the press trace."""
from __future__ import annotations

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import brnum
from ssbot.map2 import clapper as cm
from ssbot.map2 import live as lv
from ssbot.map2 import press
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

R, L, J, A, D, DS = km.B_RIGHT, km.B_LEFT, km.B_JUMP, km.B_ATTACK, km.B_DOWN, km.B_DASH
SW = ("ON", "SIDE", "FREE_POGO", "SHRINK", "SIDE_RULE", "SIDE_LAG", "XVX_MIN")


@pytest.fixture(scope="module")
def W():
    return ms.World()


@pytest.fixture(autouse=True)
def _switches():
    saved = {k: getattr(press, k)[0] for k in SW}
    yield
    for k, v in saved.items():
        getattr(press, k)[0] = v


def _air(W, y=12.0, vy=-3.0, x=30.0, face=1):
    S = km.initial_state(W.params, x, y, ground=False, facing=face)
    S[km.VY] = vy
    return S


def _without(p, bit):
    return km.HeroParams.from_json(dict(p.to_json(), hero2=p.hero2 & ~bit))


def _boxes(T, box):
    b = np.full((T, 4), np.nan)
    b[:] = box
    return b


def test_the_defaults_and_the_s1_values():
    """LiveCfg's S1b switches at their defaults set the press module's; at their S1 values S1's rules."""
    lv.set_switches(lv.LiveCfg())
    assert (press.FREE_POGO[0], press.SHRINK[0], press.SIDE_RULE[0], press.SIDE_LAG[0], press.XVX_MIN[0]) == \
        (12, 0.05, "lag", 0.5, 1.0)
    lv.set_switches(lv.LiveCfg(free_pogo=10, ds_shrink=0.0, side_rule="top0", spr_xvx=0.0))
    assert (press.FREE_POGO[0], press.SHRINK[0], press.SIDE_RULE[0], press.XVX_MIN[0]) == (10, 0.0, "top0", 0.0)
    assert km.H2_SPR_FIN == 2048 and km.H2_ALL & km.H2_SPR_FIN and km.H2_S1B == 2048


# ---- finding presses 1: the downspike lock by the bounce's cause --------------------------------------------------

def test_the_lock_credit_after_a_pogo_and_after_a_hook(W):
    """kin's lock (DS_REC ~16 f after an EV_POGO): a press it alone holds is credited from FREE_POGO (12) frames after
    a POGO onset (the game's recovery 9 - 11 f: a press at + 10 is lost in ~1 / 3 of bounces) but from FREE_MIN (10)
    after a hooked Clawline's forced bounce (its recovery 1 f: 54 / 54)."""
    S = _air(W, y=12.0, vy=0.0)
    for since, want_pogo, want_hook in ((10, "early", "lock"), (11, "early", "lock"), (12, "lock", "lock")):
        t = 1 + since
        m = np.zeros(t + 10, np.int64)
        m[t - 1] = D | A
        ev = np.zeros(len(m), np.int64)
        ev[0] = km.EV_POGO
        kt = press.trace(W, S, m, ev, [t])
        assert press.ds_start(kt, t)[1] == want_pogo, since
        assert press.ds_start(kt, t, free_min=press.FREE_MIN)[1] == want_hook, since
        assert press.ds_start(kt, t, hook_onset=1)[1] == want_hook, since     # the lock's onset is the hook's bounce
        assert press.ds_start(kt, t, hook_onset=-5)[1] == want_pogo, since    # ... another bounce's
        press.FREE_POGO[0] = 10
        assert press.ds_start(kt, t)[1] == "lock"                      # S1's rule
        press.FREE_POGO[0] = 12


def test_simulate_credits_the_slash_after_a_hook_at_control_11(W):
    """A hooked Clawline, then the down slash pressed 10 frames after its forced bounce (control + 11): credited
    (the hook's own recovery is 1 f), not 'early' as 10 frames after a pogo's bounce."""
    S = _air(W, y=10.0, vy=0.0)
    box = (36.0, 7.5, 37.5, 11.5)
    press.ON[0] = True
    plan = ms.Plan([ms.Seg(np.array([0, 0, 0, R], np.int64), [], (1, 1)),
                    ms.Seg(np.array([0] * 10 + [D | A] + [0] * 10, np.int64), [(10, 1)])])
    tr = ms.simulate(W, plan, lambda iid: _boxes(120, box), 1, S, sk.HOOK_VARIANTS[0])
    assert tr.hooks and tr.hooks[0].ok
    assert not any(m_[0] in ("dslash:early", "dslash:none") for m_ in tr.missed), tr.missed
    # the pogo's rule there (FREE_MIN as FREE_POGO): the same press is 'early'
    fm = press.FREE_MIN
    try:
        press.FREE_MIN = press.FREE_POGO[0]
        tr = ms.simulate(W, plan, lambda iid: _boxes(120, box), 1, S, sk.HOOK_VARIANTS[0])
    finally:
        press.FREE_MIN = fm
    assert any(m_[0] == "dslash:early" for m_ in tr.missed), tr.missed


# ---- finding presses 2: the contact's slack ----------------------------------------------------------------------

def test_a_contact_on_a_sliver_is_not_a_pogo(W):
    """Both slash alternations must meet the body box shrunk by SHRINK (0.05 u): a box that the polygons only graze
    (by 0.01 u) is no contact - with SHRINK 0 (S1) it was."""
    face = np.ones(12, np.int64)
    gnd = np.zeros(12, bool)
    pos = np.tile(np.array([[30.0, 10.0]]), (12, 1))
    # a body under her whose top the slashes' lowest points (DOWN 2.676, DOWN_ALT 2.602 below her) just reach: the
    # DOWN_ALT alternation by 0.01 u
    box = np.tile(np.array([[29.5, 5.0, 30.5, 10.0 - 2.602 + 0.01]]), (12, 1))
    c0 = sk.dslash_contact(pos, face, gnd, 1, box, 0.0)
    c1 = sk.dslash_contact(pos, face, gnd, 1, box, 0.05)
    assert c0 > 0 and c1 < 0
    box[:, 3] = 10.0 - 2.602 + 0.3                             # 0.3 u deep: a contact either way
    assert sk.dslash_contact(pos, face, gnd, 1, box, 0.05) == c0


# ---- finding presses 3: the highest top of a frame's records -----------------------------------------------------

def test_union_tops_takes_the_highest_record_of_a_frame(W):
    """Two records of a Clapper drawn on one frame (a timing view where an offset shrinks): robust_boxes intersects
    them (the lower top), union_tops gives the higher one - the side rule's top; the array path and the record path
    agree."""
    K = W.K
    st = "Idle"
    recs = {7: [(5, 0, 0, st, 3, 33.0, cm.STAND_Y, 1, None), (5, 0, 0, st, 3, 33.0, cm.STAND_Y + 0.4, 1, None),
                (6, 0, 0, st, 4, 33.0, cm.STAND_Y, 1, None)]}
    out = []
    for on in (True, False):
        brnum.ON[0] = on
        try:
            br = cm.Branch(1.0, {}, None, recs, [], K, 20)
            rb = sk.robust_boxes(br, 7, 20)
            ut = sk.union_tops(br, 7, 20)
        finally:
            brnum.ON[0] = True
        out.append((rb.copy(), ut.copy()))
        assert ut[5] == pytest.approx(rb[5, 3] + 0.4)
        assert ut[6] == pytest.approx(rb[6, 3])
        assert np.isnan(ut[0]) and np.isnan(rb[0, 0])
    assert np.allclose(out[0][1], out[1][1], equal_nan=True)


# ---- findings others 1 / 2: the side rule -------------------------------------------------------------------------

def test_out_of_sprint_ignores_the_extra_velocitys_residue():
    """The retained extra velocity of an earlier Attack Cancel decays to 0.01 - 0.1 u/s for ~40 frames: below
    XVX_MIN (1 u/s) it no longer makes a slash 'out of the sprint'; the air sprint / dash mode always does."""
    kt = np.zeros((3, press.NCOL))
    kt[1, press.C_MODE] = km.M_NORMAL
    kt[1, press.C_XVX] = 0.012
    press.XVX_MIN[0] = 1.0
    assert not press.out_of_sprint(kt, 1)
    press.XVX_MIN[0] = 0.0
    assert press.out_of_sprint(kt, 1)                          # S1's clause
    press.XVX_MIN[0] = 1.0
    kt[1, press.C_XVX] = 6.0
    assert press.out_of_sprint(kt, 1)
    kt[1, press.C_XVX] = 0.0
    kt[1, press.C_MODE] = km.M_SPRINT
    assert press.out_of_sprint(kt, 1)


def test_side_hit_the_lag_rule():
    """'lag': the body meets her first when her hurtbox, carried SIDE_LAG further in her travel direction, overlaps
    it from the slash's start to its contact; a body she is above, or one beyond the lag, is a pogo. 'top0' (S1):
    her box bottom below the body's top at the contact, however far it is."""
    n = 10
    pos = np.zeros((n, 2))
    pos[:, 0] = 30.0 + 0.2 * np.arange(n)
    pos[:, 1] = 6.0
    hb = np.stack([pos[:, 0] - 0.25, pos[:, 1] - 1.5527, pos[:, 0] + 0.25, pos[:, 1] - 1.5527 + 2.08], axis=1)
    hw = cm.HURTBOX[0]
    c = 8
    for gap, want in ((0.3, True), (0.8, False)):
        x0 = pos[c, 0] + hw + gap                               # the body's near side ahead of her hurtbox at c
        rel = np.tile(np.array([[x0, 3.0, x0 + 1.5, 6.0]]), (n, 1))
        press.SIDE_RULE[0], press.SIDE_LAG[0] = "lag", 0.5
        k = press.side_hit(pos, rel, None, 2, c, 1, hb)
        assert (k >= 0) == want, gap
        press.SIDE_RULE[0] = "top0"
        assert press.side_hit(pos, rel, None, 2, c, 1, hb) == c      # S1: below the top -> body
        press.SIDE_RULE[0] = "lag"
        assert press.side_hit(pos, rel, None, 2, c, -1, hb) == -1    # moving away from it
    rel = np.tile(np.array([[pos[c, 0], 0.0, pos[c, 0] + 1.5, hb[c, 1] - 0.2]]), (n, 1))
    assert press.side_hit(pos, rel, None, 2, c, 1, hb) == -1         # she is above it
    tops = np.full(n, hb[c, 1] + 0.5)                                # ... but another record's top is higher
    assert press.side_hit(pos, rel, tops, 2, c, 1, hb) >= 0
    press.SIDE_RULE[0] = "top"
    assert press.side_hit(pos, rel, tops, 2, c, 1, hb) == c
    press.SIDE_RULE[0] = "top0"
    assert press.side_hit(pos, rel, tops, 2, c, 1, hb) == -1


# ---- finding others 4: the air sprint's last frame (H2_SPR_FIN) -----------------------------------------------------

def test_the_attack_queued_into_the_sprints_last_frame_swings(W):
    """An attack queued in the air sprint's L / R state with the dash released, its Wait expiring this Update: the
    Loop's entry reads the queue before its END - the Attack Cancel swings (the show recordings: DownSlashAlt on
    that frame); without H2_SPR_FIN the model took END first and lost it."""
    S = _air(W, y=12.0, vy=0.0)
    old = _without(W.params, km.H2_SPR_FIN)
    gained = 0
    for p in range(8, 30):
        m = np.array([DS | R] * 6 + [R] * (p - 6) + [R | D | A] + [R | D] * 2 + [D] * 12, np.int64)
        on = km.rollout(S, m[None], W.params, W.terr)
        off = km.rollout(S, m[None], old, W.terr)
        a_on = (on.flags[0] & km.F_ATTACKING) != 0
        a_off = (off.flags[0] & km.F_ATTACKING) != 0
        if a_off.any():
            assert a_on.any()
            # the bit changes nothing where the model already swung (the same first frame)
            assert np.argmax(a_on) == np.argmax(a_off)
        elif a_on.any():
            gained += 1
    assert gained >= 1


# ---- findings others 3 / 7: the late check's world, its press scan, the Cogfly keys ---------------------------------

@pytest.fixture(scope="module")
def live_plan(W):
    C = 33.0
    sit = ms.Situation(km.initial_state(W.params, C - 7.0, sk.FLOOR + sk.FOOT, ground=True, facing=1),
                       [cm.Obs(1, "Idle", 8 / 60.0, C, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=8)], {1: cm.Memory()})
    S = lv._Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
    S.vclock = 0.002
    cfg = lv.LiveCfg(prio="as", cap_min=1.5, cap_fb=1.5, deadline=False)
    snap = {"seq": 1, "ep": 0, "f": 100, "fo": 100, "S": sit.S, "cmds": np.array([0, R, R, R, R, R], np.int64),
            "n_inflight": 1, "hold": lv.hold_tuple(km.HoldState.idle(1)), "lat_s": 0, "presses": [],
            "obs": sit.obs, "mems": sit.mems, "hazards": sit.hazards, "ctrl": None, "trig": [], "busy": None}
    sent = []
    lp = lv._search_one(S, cfg, snap, 0, {}, lambda: False, send=sent.append)
    if not isinstance(lp, lv.LivePlan):
        lp = sent[-1]
    return sit, lp


def test_late_check_from_the_commits_state(W, live_plan):
    """base: the commit's own state (frame s from the anchor, its hold filter state and latched mask) and the keys
    applied since it - the same verdict as from the anchor when that state is the anchor world's; an unplanned press
    BEFORE the base (the fallback's, in the past at the commit) no longer fails it, one after it does."""
    sit, lp = live_plan
    o0 = max(range(len(lp.outs)), key=lambda i: lp.outs[i].p)
    o = lp.outs[o0]
    f = 106
    keys = np.array([int(o.cmds[k]) for k in range(1, f + 2 - 100)], np.int64)
    sb = 3
    # the anchor world's state at frame sb: the outcome's own path through the same keys
    lat = lv.hold_filter1(np.concatenate([keys, o.cmds[f + 2 - 100:o.end + 1]]), lp.hold_a)
    hold_b = lv.hold_tuple(km.HoldState.idle(1))
    plan, why = lv.reanchor_outcome(o, 0, lat, lp.lat_a)
    assert plan is not None, why
    tr = ms.simulate(W, plan, lambda iid: o.boxes.get(iid), 1, lp.S_a, lv.VARIANTS[o.variant], 0)
    st = ms.state_at(W, tr, sb)
    assert st is not None
    base = {"s": sb, "S": st[0], "hold": hold_b, "lat": int(lat[sb - 1])}
    ok0, why0, info0 = lv.late_check(W, lp, 104, f, keys, [o0], 0.5)
    ok1, why1, info1 = lv.late_check(W, lp, 104, f, keys[sb:], [o0], 0.5, base=base)
    assert ok0 and ok1, (why0, why1)
    assert info1["base"] == sb
    bad = keys.copy()
    bad[0] |= km.B_ATTACK                                       # frame t_a + 1: before the base
    ok, why, _ = lv.late_check(W, lp, 104, f, bad, [o0], 0.5)
    assert not ok and why == "unplanned slash"                  # S1: from the anchor
    ok, why, _ = lv.late_check(W, lp, 104, f, bad[sb:], [o0], 0.5, base=base)
    assert ok, why
    bad = keys.copy()
    bad[sb + 1] |= km.B_ATTACK                                  # after the base
    ok, why, _ = lv.late_check(W, lp, 104, f, bad[sb:], [o0], 0.5, base=base)
    assert not ok and why == "unplanned slash"


class _Trk:
    def __init__(self, obs):
        self.o = obs

    def obs(self):
        return self.o


def test_the_controllers_late_check_uses_the_commit_base_and_strips_the_cogfly(W, live_plan, monkeypatch):
    """_late with late_base: the keys from the commit's frame on (a Cogfly throw's Up + QuickCast stripped, as the
    audit and the keys in flight strip them) and the commit's base; late_base off: S1's (from the anchor, as sent)."""
    sit, lp = live_plan
    o0 = max(range(len(lp.outs)), key=lambda i: lp.outs[i].p)
    o = lp.outs[o0]
    calls = []

    def fake(W_, lp_, fo, f, keys, idx, tol, pos_ref=None, slip=None, base=None):
        calls.append(([int(x) for x in keys], base))
        return True, "ok", {"alive": list(idx), "pos_over": {}}
    monkeypatch.setattr(lv, "late_check", fake)
    for late_base in (True, False):
        ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", log=False, replay=True, late_base=late_base))
        ctl.trk = _Trk(sit.obs)
        ctl.ctrl, ctl.ctrl_idx, ctl.ctrl_pos, ctl.ctrl_since = lp, [o0], {}, 100
        ctl.ctrl_base = {"s": 2, "S": lp.S_a, "hold": lp.hold_a, "lat": 0}
        for k in range(101, 104):
            ctl.sent_hist[k] = int(o.cmds[k - 100]) ^ R               # every frame a slip
        ctl.sent_hist[103] |= lv.COG
        ctl.own_hist[103] = "cog"
        calls.clear()
        ctl._late(101, 104, 103, {})
        assert calls
        keys, base = calls[-1]
        if late_base:
            assert base is ctl.ctrl_base and len(keys) == 104 + 2 - (100 + 2 + 1)
            assert all((k & lv.COG) != lv.COG for k in keys)
        else:
            assert base is None and len(keys) == 104 + 2 - 101
            assert any((k & lv.COG) == lv.COG for k in keys)


# ---- finding others 2: the bot side's warm-up ---------------------------------------------------------------------

def test_warm_loads_the_press_trace_and_the_strike_paths(W, monkeypatch):
    """Map2Controller.warm() runs the press trace and a simulate with a credited down slash and a hooked Clawline
    (their compiled code loaded before the first commit check)."""
    n = {"trace": 0, "hook": 0}
    tr0, hk0 = press.trace, sk.claw_hook

    def tr(*a, **k):
        n["trace"] += 1
        return tr0(*a, **k)

    def hk(*a, **k):
        n["hook"] += 1
        return hk0(*a, **k)
    monkeypatch.setattr(press, "trace", tr)
    monkeypatch.setattr(sk, "claw_hook", hk)
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", log=False))
    ctl.warm()
    assert n["trace"] >= 3 and n["hook"] >= 2
