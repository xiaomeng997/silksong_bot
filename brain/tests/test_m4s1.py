"""Map v2 stage M4 S1: the safety fixes before the w7 gate (HANDOFF 'Task map2 - stage M4' / 'S1', forum.md 100) - the
press validity (a strike credited only when her kin state starts it: ssbot.map2.press, the search's realizer and
simulate), the low side down slash out of the air sprint (the body's contact, not a pogo), the air dash restored by a
pogo bounce (HERO2 H2_POGO_DASH: kin_jit and the estimator), the Clawline from the air sprint (H2_CLAW_SPR) and the
late tick (the plan in control re-checked from the keys actually sent)."""
from __future__ import annotations

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import env_jit as ej
from ssbot.map2 import live as lv
from ssbot.map2 import press
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

R, L, J, A, D, DS = km.B_RIGHT, km.B_LEFT, km.B_JUMP, km.B_ATTACK, km.B_DOWN, km.B_DASH
C = 33.0
IDLE_H = lv.hold_tuple(km.HoldState.idle(1))


@pytest.fixture(scope="module")
def W():
    return ms.World()


@pytest.fixture(autouse=True)
def _switches():
    on, side = press.ON[0], press.SIDE[0]
    yield
    press.ON[0], press.SIDE[0] = on, side


def _air(W, y=12.0, vy=-3.0, x=30.0, face=1):
    S = km.initial_state(W.params, x, y, ground=False, facing=face)
    S[km.VY] = vy
    return S


def _without(p, bit):
    return km.HeroParams.from_json(dict(p.to_json(), hero2=p.hero2 & ~bit))


# ---- the air dash after a pogo (H2_POGO_DASH) ------------------------------------------------------------------

def test_a_pogo_restores_the_air_dash(W, monkeypatch):
    """DownspikeBounce -> ResetAirMoves (M0 28 / 28, M4a 11 / 11): kin_jit's EV_POGO clears AIRDASHED with the bit; the
    bit off (SSBOT_FORUM_HERO2_OFF=1536: M4d2's model) keeps it spent."""
    p = W.params
    assert p.hero2 & km.H2_POGO_DASH and p.hero2 & km.H2_CLAW_SPR and km.H2_S1 == 1536
    m = np.array([DS | R] * 6 + [R] * 6, np.int64)
    ev = np.zeros(len(m), np.int64)
    ev[8] = km.EV_POGO
    S = _air(W, vy=0.0)
    assert W.roll(S, m).final[km.AIRDASHED, 0] == 1.0
    assert W.roll(S, m, ev).final[km.AIRDASHED, 0] == 0.0
    old = _without(p, km.H2_POGO_DASH)
    r = km.rollout(S, m[None], old, W.terr, events=ev[None])
    assert r.final[km.AIRDASHED, 0] == 1.0
    monkeypatch.setenv(km.HERO2_OFF_ENV, "1536")
    assert km.hero2(km.HeroParams.load(km.REPO / "knowledge" / "1.0.30000" / "kinematics" /
                                       "hero_wanderer_forum.json"), on=True).hero2 & km.H2_S1 == 0


def _rows(params, flags_seq, modes):
    fr = km.ForumRows(params)
    out = []
    for fl, md in zip(flags_seq, modes):
        S = np.zeros(km.K)
        r = {"dt": 1.0 / 60.0, "fs": 1, "facing": 1, "wall": 0, "clip": "Airborne", "tm": None, "mask": 0,
             "vel": np.array([0.0, -1.0]), "udt": 1.0 / 60.0}
        fr.push(S, r, md, lambda name, fl=fl: bool(fl.get(name, False)))
        out.append(S[km.AIRDASHED])
    return out


def test_the_estimator_restores_the_air_dash_at_the_bounce_onset(W):
    """ForumRows (state_table / StateTracker): an air dash spends it; the onset of cState.downSpikeBouncing (a pogo,
    a hooked Clawline's control) restores it with H2_POGO_DASH - before, only the ground / a wall slide did."""
    fl = [{}, {}, {}, {"downSpikeBouncing": True}, {"downSpikeBouncing": True}, {}]
    md = [km.M_NORMAL, km.M_DASH, km.M_NORMAL, km.M_NORMAL, km.M_NORMAL, km.M_NORMAL]
    assert _rows(W.params, fl, md) == [0.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    assert _rows(_without(W.params, km.H2_POGO_DASH), fl, md) == [0.0, 1.0, 1.0, 1.0, 1.0, 1.0]


# ---- the Clawline from the air sprint (H2_CLAW_SPR) ---------------------------------------------------------------

def test_claw_allowed_in_the_air_sprint(W):
    """M4a: the Clawline at once from any air-sprint frame (29 / 29); the dash's own steps and the umbrella's antic /
    inflate: no; the bit off: M4d2's rule (normal control, the float / deflate)."""
    P = W.params.vector()
    P0 = _without(W.params, km.H2_CLAW_SPR).vector()
    cu = np.array([-1.0, 0, 0, 0, 0, 0, 0])
    x = _air(W)
    for (m, ph, want, want0) in ((km.M_NORMAL, 0, True, True), (km.M_SPRINT, 0, True, False),
                                 (km.M_SPRINT, 1, True, False), (km.M_SPRINT, 2, False, False),
                                 (km.M_DASH, 0, False, False), (km.M_GLIDE, 0, False, False),
                                 (km.M_GLIDE, 1, False, False), (km.M_GLIDE, 2, True, True)):
        x[km.MODE], x[km.PHASE] = m, ph
        assert ej.claw_allowed(x, cu, P) == want, (m, ph)
        assert ej.claw_allowed(x, cu, P0) == want0, (m, ph)
    cu[ej.C_CLOCK] = 3.0
    x[km.MODE], x[km.PHASE] = km.M_NORMAL, 0
    assert not ej.claw_allowed(x, cu, P)


# ---- the press check (ssbot.map2.press) ---------------------------------------------------------------------------

def test_press_trace_matches_the_rollout(W):
    rng = np.random.default_rng(5)
    keys = [0, L, R, J, J | L, DS | R, A | D, A | D | J, DS | L, A | D | DS]
    for _ in range(60):
        S = _air(W, y=float(rng.uniform(6, 14)), vy=float(rng.uniform(-8, 4)))
        T = int(rng.integers(5, 40))
        m = np.zeros(T, np.int64)
        cur = 0
        for i in range(T):
            if rng.random() < 0.3:
                cur = int(rng.choice(keys))
            m[i] = cur
        r = W.roll(S, m)
        kt = press.trace(W, S, m)
        assert np.array_equal((r.flags[0] & km.F_ATTACKING) != 0, kt[:, press.C_ATK] > 0)


def test_ds_start_where_the_game_starts_the_slash(W):
    """A down slash pressed: in normal control at once; in the umbrella's antic nothing; in its float only with the
    jump held on the press frame (its release closes the umbrella first: H2_REL_LOSS); in the air sprint queued to the
    sprint's Attack Cancel - a down slash when down is still held then, else a side slash."""
    def ds(m, t, S=None):
        kt = press.trace(W, _air(W) if S is None else S, np.array(m, np.int64), None, [t])
        return press.ds_start(kt, t)
    assert ds([0, 0, D | A] + [0] * 8, 3) == (3, "down")
    assert ds([J] * 3 + [J | D | A] + [0] * 8, 4)[1] == "none"                  # the umbrella's antic
    assert ds([J] * 21 + [D | A] + [0] * 10, 22) == (22, "none")                # the float, jump released
    assert ds([J] * 21 + [J | D | A] + [0] * 10, 22) == (22, "down")            # ... held
    S = _air(W, vy=0.0)
    m_rel = [DS | R] * 5 + [DS | R | D | A] + [DS | R] * 2 + [R] * 8
    m_hold = [DS | R] * 5 + [DS | R | D | A] + [DS | R | D] * 6 + [R] * 8
    t_r, k_r = ds(m_rel, 6, S)
    t_h, k_h = ds(m_hold, 6, S)
    assert k_r == "side" and k_h == "down" and t_h == t_r > 6
    kt = press.trace(W, S, np.array(m_hold, np.int64))
    assert press.out_of_sprint(kt, t_h)


def _boxes(T, box):
    b = np.full((T, 4), np.nan)
    b[:] = box
    return b


def test_simulate_credits_only_slashes_the_kin_state_starts(W):
    """The float's press with the jump released: no slash in the game - credited before S1 (the geometry alone),
    a miss now ('dslash:none'); held: credited."""
    S = _air(W, y=10.0)
    t = 22
    for held, want in ((False, 0), (True, 1)):
        m = np.array([J] * (t - 1) + [(J if held else 0) | D | A] + [0] * 10, np.int64)
        r = W.roll(S, m)
        x, y = r.pos[0, t + 4]
        box = (x - 0.6, y - 3.2, x + 0.6, y - 1.6)                 # a body under her at the swing's frames
        plan = ms.Plan([ms.Seg(m, [(t - 1, 1)])])
        press.ON[0] = True
        tr = ms.simulate(W, plan, lambda iid: _boxes(60, box), 1, S, sk.HOOK_VARIANTS[0])
        assert len([c for c in tr.contacts if c[2] == "down"]) == want, (held, tr.missed)
        if not held:
            assert tr.missed and tr.missed[0][0] == "dslash:none"
            press.ON[0] = False
            tr0 = ms.simulate(W, plan, lambda iid: _boxes(60, box), 1, S, sk.HOOK_VARIANTS[0])
            assert len(tr0.contacts) == 1                         # M4d2's search credited it


def test_a_side_contact_out_of_the_air_sprint_is_the_bodys(W):
    """LEAD NOTE 3 (a): an air dash -> sprint, a down slash out of it beside a body (her box bottom below its top):
    not a pogo - a forced collision at the contact (the 4 real hits of the airceil stage2b); above the body: a pogo."""
    S = _air(W, y=8.0, vy=0.0)
    m = np.array([DS | R] * 5 + [DS | R | D | A] + [DS | R | D] * 6 + [R] * 10, np.int64)
    kt = press.trace(W, S, m)
    ts, kind = press.ds_start(kt, 6)
    assert kind == "down"
    r = W.roll(S, m)
    x, y = r.pos[0, ts + 4]
    bb = float(r.box[0, ts + 4, 1])
    for top, side in ((bb + 1.0, True), (bb - 0.3, False)):
        box = (x + 0.4, top - 3.0, x + 1.4, top)
        plan = ms.Plan([ms.Seg(m, [(5, 1)])])
        press.ON[0] = press.SIDE[0] = True
        tr = ms.simulate(W, plan, lambda iid: _boxes(60, box), 1, S, sk.HOOK_VARIANTS[0])
        if side:
            assert not tr.contacts and tr.bad and tr.bad[0][1] == "side_spr"
            assert ms.bad_frame(tr, 1, tr.end) == tr.bad[0][0]
        else:
            assert tr.contacts and not tr.bad
        press.SIDE[0] = False
        tr0 = ms.simulate(W, plan, lambda iid: _boxes(60, box), 1, S, sk.HOOK_VARIANTS[0])
        assert tr0.contacts and not tr0.bad


def test_a_clawline_the_state_does_not_allow_is_a_forced_collision(W):
    """A Clawline pressed in the umbrella's antic: the plan cannot be played from P (a forced collision there); from
    the air sprint (M4a, H2_CLAW_SPR) and in normal control: played; inside a previous Clawline's lock: not."""
    S = _air(W, y=10.0)
    box = (36.0, 4.0, 37.5, 8.0)
    cases = (([J] * 4 + [R], True), ([DS | R] * 6 + [R], False), ([0, 0, 0, R], False))
    for masks, bad in cases:
        plan = ms.Plan([ms.Seg(np.array(masks, np.int64), [], (1, 1))])
        press.ON[0] = True
        tr = ms.simulate(W, plan, lambda iid: _boxes(80, box), 1, S, sk.HOOK_VARIANTS[0])
        assert bool(tr.bad) == bad, (masks, tr.bad)
        if bad:
            assert tr.bad[0] == (len(masks), "claw_state")
    plan = ms.Plan([ms.Seg(np.array([0, 0, 0, R], np.int64), [], (1, 1))])
    tr = ms.simulate(W, plan, lambda iid: _boxes(80, box), 1, S, sk.HOOK_VARIANTS[0], claw_lock=6)
    assert tr.bad == [(4, "claw_state")]


def test_the_realizer_keeps_the_held_jump_on_the_press_frame(W):
    """The witness floats in the umbrella (jump held): M3's press let the jump go on the press frame (the slash lost);
    the S1 realizer keeps it there and the kin state starts the down slash."""
    Sx = ms.Searcher(W, ms.Cfg())
    node = ms.Node(ms.Plan([], "prim"), 0, _air(W, y=10.0), None)
    masks = np.array([J] * 21, np.int64)
    press.ON[0] = True
    seg = Sx._realize_ds(node, masks, 21, 1, 4)
    assert seg is not None and seg.dsl == [(21, 1)]
    assert seg.masks[21] & J and seg.masks[21] & D and seg.masks[21] & A
    kt = press.trace(W, node.S, seg.masks, None, [22])
    assert press.ds_start(kt, 22) == (22, "down")
    # in the umbrella's antic no variant starts one: rejected
    assert Sx._realize_ds(node, np.array([J] * 3, np.int64), 3, 1, 4) is None


# ---- the late tick ------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live_plan(W):
    sit = ms.Situation(km.initial_state(W.params, C - 7.0, sk.FLOOR + sk.FOOT, ground=True, facing=1),
                       [cm.Obs(1, "Idle", 8 / 60.0, C, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=8)], {1: cm.Memory()})
    S = lv._Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
    S.vclock = 0.002
    cfg = lv.LiveCfg(prio="as", cap_min=1.5, cap_fb=1.5, deadline=False)
    snap = {"seq": 1, "ep": 0, "f": 100, "fo": 100, "S": sit.S, "cmds": np.array([0, R, R, R, R, R], np.int64),
            "n_inflight": 1, "hold": IDLE_H, "lat_s": 0, "presses": [], "obs": sit.obs, "mems": sit.mems,
            "hazards": sit.hazards, "ctrl": None, "trig": [], "busy": None}
    sent = []
    lp = lv._search_one(S, cfg, snap, 0, {}, lambda: False, send=sent.append)
    if not isinstance(lp, lv.LivePlan):
        lp = sent[-1]
    return sit, lp


def test_late_check_from_the_keys_actually_sent(W, live_plan):
    """A skipped tick held the previous keys for a frame: the plan in control re-simulated from its anchor with the
    keys actually sent - as planned: ok (its own path); its keys a frame late everywhere (a slip of every change):
    judged on the path / the danger; a press it does not have: rejected."""
    sit, lp = live_plan
    o0 = max(range(len(lp.outs)), key=lambda i: lp.outs[i].p)
    o = lp.outs[o0]
    f = 106
    keys = np.array([int(o.cmds[k]) for k in range(1, f + 2 - 100)], np.int64)
    ok, why, info = lv.late_check(W, lp, 104, f, keys, [o0], 0.5)
    assert ok, (why, info)
    assert info["dev"] < 1e-6
    bad = keys.copy()
    bad[3] |= km.B_ATTACK
    ok, why, _ = lv.late_check(W, lp, 104, f, bad, [o0], 0.5)
    assert not ok and why == "unplanned slash"
    late = np.concatenate([[int(o.cmds[0]) if len(o.cmds) else 0], keys[:-1]])
    slip = [100 + q + 1 for q in range(len(keys)) if late[q] != keys[q]]
    ok, why, info = lv.late_check(W, lp, 104, f, late, [o0], 0.0, slip=slip)
    assert (not ok and why in ("path", "danger", "claw latch", "press moved")) or (ok and info["dev"] == 0.0)
    # the slip's own effect only: the same late keys with no slip named - the effect is 0 (a model drift or a replay's
    # recorded position never counts)
    ok, why, info = lv.late_check(W, lp, 104, f, late, [o0], 0.0, slip=[])
    assert why != "path"


def test_a_bad_press_up_to_the_deviation_is_unsafe(W):
    """A Clawline the state does not allow (the umbrella's antic) is the plan's own press: the outcome is unsafe
    ('press@P') - M3 accepts a collision AT the deviation frame, but the plan's key there is still played."""
    sit = ms.Situation(_air(W, y=10.0), [cm.Obs(1, "Idle", 8 / 60.0, 40.0, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=8)],
                       {1: cm.Memory()})
    press.ON[0] = True
    plan = ms.Plan([ms.Seg(np.array([J] * 4 + [R], np.int64), [], (1, 1))])
    ev = ms.Searcher(W, ms.Cfg()).ev.evaluate(sit, plan, exits=False)
    assert ev.outcomes and not ev.safe
    assert all(o.why == "press@5" for o in ev.outcomes)


class _Trk:
    def __init__(self, obs):
        self.o = obs
        self.cl = {ob.iid: {"st": ob.st, "ent": 0, "e": {}} for ob in obs}

    def obs(self):
        return self.o

    def feed(self, raw, g):
        pass

    def mems(self):
        return {ob.iid: cm.Memory() for ob in self.o}

    def hazards(self, K):
        return []


def test_the_controller_rechecks_a_slipped_key(W, live_plan, monkeypatch):
    """The plan in control, a tick skipped: no slip (the held key is the plan's) - nothing; a slip - late_check runs
    and its verdict decides (a failed one drops the plan: 'late')."""
    sit, lp = live_plan
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", log=False, replay=True))
    ctl.trk = _Trk(sit.obs)
    o0 = max(range(len(lp.outs)), key=lambda i: lp.outs[i].p)
    o = lp.outs[o0]
    ctl.ctrl, ctl.ctrl_idx, ctl.ctrl_pos, ctl.ctrl_since = lp, [o0], {}, 100
    for k in range(101, 104):
        ctl.sent_hist[k] = int(o.cmds[k - 100])
    calls = []

    def fake(W_, lp_, fo, f, keys, idx, tol, pos_ref=None, slip=None, **kw):
        calls.append((fo, f, [int(x) for x in keys], slip))
        return False, "danger", {"s": fo - lp_.t_a}
    monkeypatch.setattr(lv, "late_check", fake)
    row: dict = {}
    # frames 104 .. 105 got no ACTION (held 103's keys)
    want = {int(o.cmds[k - 100]) for k in (104, 105)}
    res = ctl._late(101, 104, 103, row)
    slipped = any(w != int(o.cmds[3]) for w in want)
    assert (res == "late") == slipped and bool(calls) == slipped
    if slipped:
        assert ctl.ctrl is None and row["late"]
