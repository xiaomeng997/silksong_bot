"""Map v2 stage E2 (HANDOFF 'Task map2 - the evaluation and the handover - stage E2', forum.md 108): the handover the
w7 gate exposed - the plan as a tube (a Clapper's transition a frame late re-checked exactly on its observed timing
instead of a drop; her x corridor), re-planning from mid-swing (search.simulate's swing; the commit check carries
it), the swing hold after a drop mid-swing, the baseline plan (the search's escape probes; the worker sends one
instead of the noop). Every switch default off."""
from __future__ import annotations

import pickle
import queue
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import live as lv
from ssbot.map2 import press
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

C = 32.0
IDLE_H = lv.hold_tuple(km.HoldState.idle(1))


@pytest.fixture(scope="module")
def W():
    return ms.World()


@pytest.fixture(autouse=True)
def _switches():
    lv.set_switches(lv.LiveCfg())
    yield
    lv.set_switches(lv.LiveCfg())


def _obs(st, x, face=-1, j=2, iid=1):
    return cm.Obs(iid, st, j / 60.0, x, cm.STAND_Y, 0.0, 0.0, face, 230, None, will_evade=None, j=j)


def _ground(W, x, face=1):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, facing=face)


def _snap(sit, fo=100, cmds=(0, 0), n_inflight=1, seq=1, ctrl=None):
    return {"seq": seq, "ep": 0, "f": fo, "fo": fo, "S": sit.S, "cmds": np.asarray(cmds, np.int64),
            "n_inflight": n_inflight, "hold": IDLE_H, "lat_s": 0, "presses": [], "obs": sit.obs, "mems": sit.mems,
            "hazards": sit.hazards, "ctrl": ctrl, "trig": [], "busy": None}


class _Trk:
    def __init__(self, obs):
        self.o = obs
        self.cl = {o.iid: {"st": o.st, "ent": 0, "e": {}} for o in obs}

    def obs(self):
        return self.o

    def mems(self):
        return {o.iid: cm.Memory() for o in self.o}

    def hazards(self, K):
        return []


def _obs_at(o, n, shift=None):
    """The Clappers of an outcome at frame n as Obs (its own records); shift (d, t0): its transition at t0 d frames
    late - the record of frame n - d at and after t0 + d, the one of t0 - 1 (its frame in state run on) in the gap."""
    inv = {v: k for k, v in o.sids.items()}
    out = []
    for iid, (ks, st, j, x, f) in o.vrecs.items():
        m, dj = n, 0
        if shift is not None:
            d, t0 = shift
            if t0 <= n < t0 + d:
                m, dj = t0 - 1, n - (t0 - 1)
            elif n >= t0 + d:
                m = n - d
        a = int(np.searchsorted(ks, m))
        if a < len(ks) and ks[a] == m:
            out.append(cm.Obs(iid, inv[int(st[a])], float(j[a] + dj) / 60.0, float(x[a]), cm.STAND_Y, 0.0, 0.0,
                              int(f[a]), 230, None, j=int(j[a] + dj)))
    return out


@pytest.fixture(scope="module")
def live_plan(W):
    """A LivePlan from a forced situation: her 7 u from an Idle Clapper (test_m4c_live's)."""
    sit = ms.Situation(_ground(W, C - 7.0), [_obs("Idle", C, face=-1, j=8)], {1: cm.Memory()})
    S = lv._Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
    cfg = lv.LiveCfg(prio="as", cap_min=1.5, cap_fb=1.5)
    lp = lv._search_one(S, cfg, _snap(sit), 0, {}, lambda: False)
    assert isinstance(lp, lv.LivePlan), lp
    return sit, lp


def _transition(o, lo=3):
    """The first frame t0 >= lo of the outcome's committed part where its Clapper's state changes (None: none)."""
    for iid, (ks, st, j, x, f) in o.vrecs.items():
        for a in range(1, len(ks)):
            if ks[a] >= lo and ks[a] <= o.kc - 2 and st[a] != st[a - 1] and ks[a] == ks[a - 1] + 1:
                return int(iid), int(ks[a])
    return None


# ---- (b) the swing carried into a plan -------------------------------------------------------------------------------

def test_a_swing_carried_into_a_plan_is_the_full_simulation(W):
    """A down slash pressed before the plan's start (her kin state mid-swing: ATTACKING, ATK_T, ATK_PDIR 2) is
    credited as if it were pressed inside the plan: the same contact frame, bounce, path and pogo i-frames; from the
    bounce's first frame on, only its i-frames are carried."""
    Sa = km.initial_state(W.params, 30.0, sk.FLOOR + 3.0 + sk.FOOT, ground=False, vy=-2.0, facing=1)
    md = np.array([0, 0, km.B_DOWN | km.B_ATTACK, km.B_DOWN] + [0] * 30, np.int64)
    body = np.tile(np.array([[29.0, sk.FLOOR, 31.0, sk.FLOOR + 2.4]]), (90, 1))
    tr = ms.simulate(W, ms.Plan([ms.Seg(md, [(2, 7)])]), lambda iid: body, 1, Sa, sk.HOOK_VARIANTS[0], 0)
    assert [c[0] for c in tr.contacts] == [6]
    for k in (4, 5, 6):
        S_k, _ = ms.state_at(W, tr, k)
        sw = ms.swing_from_state(S_k, [7], W.params.frame_time)
        assert sw is not None
        tr2 = ms.simulate(W, ms.Plan([ms.Seg(md[k:].copy(), [])]), lambda iid: body[k:], 1, S_k, sk.HOOK_VARIANTS[0],
                          0, swing=sw)
        np.testing.assert_allclose(tr2.pos[1:20], tr.pos[k + 1:k + 20], atol=1e-9)
        assert np.array_equal(tr2.ifr[1:12], tr.ifr[k + 1:k + 12])
        if k < 6:
            assert [c[0] + k for c in tr2.contacts] == [6] and sw[0] == 3 - k and sw[2] == 0
        else:
            assert tr2.contacts == [] and sw == (0, (), 8)     # the bounce under way: its i-frames only
        tr3 = ms.simulate(W, ms.Plan([ms.Seg(md[k:].copy(), [])]), lambda iid: body[k:], 1, S_k, sk.HOOK_VARIANTS[0],
                          0)
        if k < 6:
            assert tr3.contacts == []                           # without it the swing is lost (M4c's root)
    S0 = km.initial_state(W.params, 30.0, sk.FLOOR + 3.0, ground=False)
    assert ms.swing_from_state(S0, [7], W.params.frame_time) is None


def test_the_evaluator_reads_the_swing_from_the_situation(W):
    """Situation.meta 'swing' (the live worker's snapshot, LiveCfg.midswing) reaches every simulation of the search."""
    Sa = km.initial_state(W.params, 30.0, sk.FLOOR + 3.0 + sk.FOOT, ground=False, vy=-2.0, facing=1)
    md = np.array([0, 0, km.B_DOWN | km.B_ATTACK, km.B_DOWN] + [0] * 30, np.int64)
    tr = ms.simulate(W, ms.Plan([ms.Seg(md, [])]), lambda iid: None, 1, Sa, sk.HOOK_VARIANTS[0], 0)
    S4, _ = ms.state_at(W, tr, 4)
    sit = ms.Situation(S4, [_obs("Idle", 30.0, j=20)], {1: cm.Memory()})
    assert ms.swing_of(sit) is None
    sit.meta["swing"] = ms.swing_from_state(S4, [1], W.params.frame_time)
    assert ms.swing_of(sit) == (-1, (1,), 0)


# ---- (a) the plan as a tube -----------------------------------------------------------------------------------------

def test_shift_outcome_delays_a_transition(live_plan):
    """shift_outcome (d, t0): the state before t0 runs on d frames (its frame in state counting on), everything from
    t0 on d frames later - the records, the danger rows, the targets' boxes, the committed end; match_shift finds that
    shift from the observation of the state running on."""
    sit, lp = live_plan
    cfg = lv.LiveCfg(prio="as")
    found = 0
    for o in lp.outs:
        tt = _transition(o)
        if tt is None:
            continue
        iid, t0 = tt
        c = lv.shift_outcome(o, {iid: (1, t0)})
        ks, st, j, x, f = o.vrecs[iid]
        ks2, st2, j2, x2, f2 = c.vrecs[iid]
        a = int(np.searchsorted(ks, t0 - 1))
        b = int(np.searchsorted(ks2, t0))
        assert st2[b] == st[a] and j2[b] == j[a] + 1                        # the state before t0 one frame longer
        a2 = int(np.searchsorted(ks, t0))
        b2 = int(np.searchsorted(ks2, t0 + 1))
        assert st2[b2] == st[a2] and j2[b2] == j[a2]                         # the next state one frame later
        off, BX, IIDB = o.geo[:3]
        off2, BX2, IIDB2 = c.geo[:3]
        r_old = BX[off[t0 - 1]:off[t0]][IIDB[off[t0 - 1]:off[t0]] == iid]
        r_new = BX2[off2[t0]:off2[t0 + 1]][IIDB2[off2[t0]:off2[t0 + 1]] == iid]
        np.testing.assert_array_equal(np.sort(r_old, axis=0), np.sort(r_new, axis=0))
        assert c.kc == min(o.kc + 1, o.end) and c._orig is o
        obs = _obs_at(o, t0, shift=(1, t0))
        assert lv.match_shift(o, t0, obs[0], cfg, 3) in ((1, t0), (0, 0))
        assert lv._clappers_ok(c, t0, obs, cfg)
        found += 1
    assert found


def test_the_tube_drops_when_the_recheck_is_unsafe(W, live_plan):
    """Outside the tube with no timing that matches the observed Clapper: dropped ('fail:tube:clappers')."""
    sit, lp0 = live_plan
    lp = lv.LivePlan(**{**lp0.__dict__, "outs": [o for o in lp0.outs]})
    o0 = max(lp.outs, key=lambda o: o.p)
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=1, log=True, replay=True, tube=True))
    ctl.attach_inproc([queue.Queue()], queue.Queue())
    ctl.reset(0)
    ctl.ctrl, ctl.ctrl_idx, ctl.ctrl_pos, ctl.ctrl_since = lp, list(range(len(lp.outs))), {}, 100
    raw = {"hero": {"pos": [float(o0.pos[2, 0]), float(o0.pos[2, 1])], "hero_accepting_input": True}, "dt": 1 / 60,
           "act": {"mask": 0}}
    ctl.trk = _Trk([_obs("Idle", C + 3.0, face=-1, j=8)])            # the Clapper 3 u away from every timeline
    ctl._fo_prev = 101
    assert ctl.pre(102, 102, raw, sit.S, np.array([o0.cmds[3]], np.int64), km.HoldState.idle(1)) is None
    assert ctl.row["why"].startswith("fail:tube") and ctl.ctrl is None


def test_the_corridor_and_its_window(live_plan):
    """tube_corridor: per frame the danger-free x interval around the path (the path inside it where it is safe);
    tube_window: the offsets that keep the shifted path inside it, shrunk by eps(k), capped."""
    sit, lp = live_plan
    o = max(lp.outs, key=lambda o_: o_.p)
    lo, hi = lv.tube_corridor(o, o.pos, 1)
    nk = len(lo) - 1
    ok = [k for k in range(1, nk + 1) if lo[k] <= o.pos[k, 0] <= hi[k]]
    assert len(ok) >= nk - 2
    dlo, dhi = lv.tube_window((lo, hi), o.pos, 1, 0.5)
    assert -0.5 <= dlo and dhi <= 0.5
    assert lv.eps_x([0])[0] == 0.0 and lv.eps_x([10])[0] > lv.eps_x([1])[0] > 0.0


# ---- the gate's P2 (a), (b), (c) ----------------------------------------------------------------------------------

P2_FIXTURE = Path(r"C:\ssbot\data\m2_play\map2\ev\e2\gate\p2_fixture.pkl")


@pytest.fixture(scope="module")
def p2(W):
    """The w7 gate's P2 (M4_GATE.txt; ev/scripts/e2_fixture.py): the slam strike committed on Slam Antic j32, its
    four outcomes (two branches x the timing views, the planned contacts at 23 / 25), the recorded frames after it -
    the Clapper's Slam Antic one frame longer than the early views'."""
    if not P2_FIXTURE.exists():
        pytest.skip("the gate's P2 fixture is not on this machine")
    with open(P2_FIXTURE, "rb") as fh:
        fx = pickle.load(fh)
    sit = ms.Situation(fx["S"], list(fx["obs"]), dict(fx["mems"]), list(fx["hazards"]))
    plan = ms.Plan([ms.Seg(np.asarray(fx["masks"], np.int64), list(fx["dsl"]), None, "gate")], "prim")
    S = ms.Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
    e = S.ev.evaluate(sit, plan)
    assert e.safe and len(e.outcomes) == 4
    assert sorted(c[0] for o in e.outcomes for c in o.tr.contacts) == [23, 23, 25, 25]
    return fx, sit, e


def _p2_plan(fx, e):
    return lv.LivePlan(pid="p2", t_a=int(fx["t_a"]), outs=lv.build_outs(e), plan=e.plan, n_pre=int(fx["n_pre"]),
                       ms=0.0, ep=0, S_a=np.asarray(fx["S"], float).reshape(km.K, -1)[:, 0].copy(),
                       hold_a=fx["hold"], lat_a=int(fx["lat_s"]), claw_lock=-99)


def _p2_run(W, fx, e, cfg, n_end=26):
    """The controller over the recorded frames of P2 from its commit: (the per-tick whys, the counters)."""
    lv.set_switches(cfg)
    lp = _p2_plan(fx, e)
    ctl = lv.Map2Controller(cfg=cfg)
    ctl.attach_inproc([queue.Queue()], queue.Queue())
    ctl.reset(0)
    n_c = int(fx["commit"] - fx["t_a"])
    fr = fx["frames"]
    ctl.ctrl, ctl.ctrl_idx, ctl.ctrl_pos, ctl.ctrl_since = lp, list(range(len(lp.outs))), {}, int(fx["commit"])
    ctl.ctrl_base = {"s": n_c, "S": fr[n_c]["S"], "hold": fr[n_c]["hold"], "lat": int(fr[n_c]["lat"])}
    for k in range(n_c - 2, n_c + 2):
        ctl.sent_hist[int(fx["t_a"]) + k] = int(fr[k]["act"]) if k in fr else 0
    whys = []
    for n in range(n_c, n_end):
        if n not in fr or n + 1 not in fr:
            break
        f = int(fx["t_a"]) + n
        raw = {"hero": {"pos": fr[n]["her"], "hero_accepting_input": True}, "dt": 1 / 60,
               "act": {"mask": int(fr[n]["lat"])}}
        ctl.trk = _Trk(fr[n]["obs"])
        ctl._fo_prev = f - 1
        hs = km.HoldState(*(np.asarray(x)[None] for x in fr[n]["hold"]))
        infl = np.array([int(fr[n + 1]["act"])], np.int64)
        m = ctl.pre(f, f, raw, fr[n]["S"], infl, hs)
        whys.append((n, ctl.row.get("why")))
        if m is None:
            break
        ctl.post(f, f, raw, fr[n]["S"], infl, hs, int(m), "m2", None, False)
    return whys, dict(ctl.ep_c)


def test_p2_the_tube_keeps_the_slam_strike_the_old_rule_drops(W, p2):
    """P2: the old rule drops the plan at frame 23 (its first planned contact: every outcome contradicted - the early
    views a frame early); the tube keeps it to its end (the late views on their timing, the early ones re-checked on
    the observed one or inside the time widening)."""
    fx, sit, e = p2
    whys_old, _ = _p2_run(W, fx, e, lv.LiveCfg(prio="as", parts=1, log=True, replay=True))
    assert whys_old[-1] == (23, "fail:clappers"), whys_old[-4:]
    whys_t, c_t = _p2_run(W, fx, e, lv.LiveCfg(prio="as", parts=1, log=True, replay=True, tube=True))
    assert all(w in ("keep", "commit") for (n, w) in whys_t if n <= 23), whys_t[-4:]
    assert whys_t[-1] == (24, "end")                   # the committed part (to 25) played to its end


def test_p2_shift_and_match_on_the_recorded_frames(p2):
    """The early outcome observed at 23 (Slam Antic j48; its own records: Slam 0 from 22): match_shift -> its
    transition (Slam 0 drawn at 22) two frames later, (2, 22) - the late view's timing; the shifted outcome is
    consistent with the observation and its contact moves to 25."""
    fx, sit, e = p2
    outs = lv.build_outs(e)
    cfg = lv.LiveCfg(prio="as")
    obs = fx["frames"][23]["obs"]
    early = [o for o in outs if any(c[0] == 23 for c in o.contacts)]
    late = [o for o in outs if any(c[0] == 25 for c in o.contacts)]
    assert early and late
    for o in early:
        assert not lv._clappers_ok(o, 23, obs, cfg)
        d = lv.match_shift(o, 23, obs[0], cfg, 3)
        assert d == (2, 22), d                        # its Slam 0 (drawn at 22) two frames later: the late timing
        c = lv.shift_outcome(o, {obs[0].iid: d})
        assert lv._clappers_ok(c, 23, obs, cfg) and lv._exact_ok(c, 23, obs, cfg)
        assert any(k == 25 for (k, _, _) in c.contacts)
    for o in late:
        assert not lv._clappers_ok(o, 23, obs, cfg)        # the late view's gap: the antic j48 matches no record


def test_p2_the_timing_views_gap(W, p2):
    """P2's cause (Q15): the late view's records end the slam antic at 22 (j47) and start Slam 0 at 24 - frame 23 has
    no record (and no body box: the search's own danger has a one-frame hole there). views_gap (build_outs) holds the
    antic on through Slam 0's spread: every outcome is consistent at 23, the early views are contradicted on their own
    timeline (not possible), the late ones go on; the plan is no longer dropped there (the old rule + views_gap);
    views_fill closes the hole in the views' danger."""
    fx, sit, e = p2
    cfg = lv.LiveCfg(prio="as")
    obs = fx["frames"][23]["obs"]
    lv.set_switches(lv.LiveCfg(views_gap=True))
    outs = lv.build_outs(e)
    lv.set_switches(lv.LiveCfg())
    assert all(lv._clappers_ok(o, 23, obs, cfg) for o in outs)
    assert [lv._exact_ok(o, 23, obs, cfg) for o in outs] == [any(c[0] == 25 for c in o.contacts) for o in outs]
    whys, c = _p2_run(W, fx, e, lv.LiveCfg(prio="as", parts=1, log=True, replay=True, views_gap=True))
    assert all(w in ("keep", "commit") for (n, w) in whys if n <= 23) and whys[-1] == (24, "end"), whys[-4:]
    late = [o for o in e.outcomes if getattr(o.branch, "tview", "") == "late"]
    g = ms.geo(late[0].branch, True)
    assert g.off[24] - g.off[23] == 0                   # the hole (views_fill off)
    sit2 = ms.Situation(fx["S"], list(fx["obs"]), dict(fx["mems"]), list(fx["hazards"]))
    e2 = ms.Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False, views_fill=True)).ev.evaluate(sit2, e.plan)
    late2 = [o for o in e2.outcomes if getattr(o.branch, "tview", "") == "late"]
    g2 = ms.geo(late2[0].branch, True)
    assert g2.off[24] - g2.off[23] >= 1                 # held: the antic's body
    ms.Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))      # (the module switch back off)


def test_p2_the_commit_check_carries_the_swing(W, p2):
    """P2 mid-swing (the down slash pressed at 16, its contact at 23 / 25): the re-check at frame 19 is 'slash under
    way' without midswing; with it the swing is carried (search.simulate's swing) and the re-check passes on the
    late views' timing."""
    fx, sit, e = p2
    lp = _p2_plan(fx, e)
    fr = fx["frames"]
    n = 19
    late = [i for i, o in enumerate(lp.outs) if any(c[0] == 25 for c in o.contacts)]
    infl = np.array([int(fr[n + 1]["act"])], np.int64)
    args = (W, lp, int(fx["t_a"]) + n, fr[n]["S"], infl, fr[n]["hold"], int(fr[n]["lat"]), fr[n]["her"], fr[n]["obs"])
    r_off = lv.commit_check(*args, lv.LiveCfg(prio="as"), idx=late)
    r_on = lv.commit_check(*args, lv.LiveCfg(prio="as", midswing=True), idx=late)
    assert r_off[1] == "slash under way", r_off[:2]
    assert r_on[0], r_on[:2]
    assert r_on[2]["dev"] < 0.05


def test_p2_the_swing_hold_carries_the_pogo(W, p2):
    """P2 with the tube and the swing hold: the plan ends at its committed end (25: the contact frame) mid-swing - the
    hold keeps map2's keys (re-checked on the late timing) through the pogo's i-frames instead of the fallback."""
    fx, sit, e = p2
    whys, c = _p2_run(W, fx, e, lv.LiveCfg(prio="as", parts=1, log=True, replay=True, tube=True, midswing=True,
                                           swing_hold=True), n_end=32)
    assert c.get("swing_hold_start") == 1, c
    assert any(w == "swing" for (_, w) in whys), (whys[-6:], c)


# ---- (c) the swing hold ---------------------------------------------------------------------------------------------

def test_hold_cmds_keep_the_plans_keys_without_new_presses(live_plan):
    sit, lp = live_plan
    o = max(lp.outs, key=lambda o_: o_.p)
    i = lp.outs.index(o)
    hc = lv.hold_cmds(lp, [i], 1, len(o.cmds) + 3, 0)
    assert len(hc) == len(o.cmds) + 3
    pm = 0
    for m in hc:
        assert not (m & lv.M_CLAW)
        assert not (m & ~pm & (km.B_JUMP | km.B_DASH | km.B_ATTACK))      # no rising press
        pm = m
    assert hc[-1] == 0                                                     # past the plan's end: no key


# ---- (e) the baseline plan ------------------------------------------------------------------------------------------

def test_the_baseline_probes_are_candidates(W):
    """Cfg.baseline: the escape probes after the root are evaluated (origin 'base'); off: none."""
    sit = ms.Situation(_ground(W, C - 4.0), [_obs("Slam Antic", C, face=-1, j=10)], {1: cm.Memory()})
    for on in (False, True):
        S = ms.Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False, baseline=on))
        S.vclock = 0.01
        res = S.decide(sit, cap_s=0.3)
        bases = [e for e in res.tried if e is not None and e.plan.origin == "base"]
        assert bool(bases) == on
        if on:
            assert all(e.finished for e in bases)
            assert all(e.plan.n_frames() == S.cfg.base_h for e in bases)


def test_the_worker_sends_a_baseline_instead_of_the_noop(W):
    """LiveCfg.baseline: a search whose answer would be the noop (here: alt_noop off) sends its best safe escape (pid
    suffix 'b', LivePlan.base) instead of handing the keys back; off: the noop status as before. The probes that touch
    the root's danger are screened out first (a slam antic next to her: the strike plan is found as without them)."""
    sit = ms.Situation(_ground(W, C - 4.0), [_obs("Spell Antic", C, face=-1, j=20)], {1: cm.Memory()})
    got = {}
    for on in (False, True):
        cfg = lv.LiveCfg(prio="as", cap_min=0.2, cap_fb=0.2, baseline=on, alt_noop=False)
        S = lv._Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False, **lv.search_kw(cfg)))
        S.vclock = 0.01
        got[on] = lv._search_one(S, cfg, _snap(sit), 0, {}, lambda: False)
    off, onr = got[False], got[True]
    assert isinstance(off, dict) and off["status"] in ("noop", "unsafe"), off
    assert isinstance(onr, lv.LivePlan) and onr.base and onr.pid.endswith("b"), onr
    assert all(o.kc >= 1 for o in onr.outs)
    sit2 = ms.Situation(_ground(W, C - 3.0), [_obs("Slam Antic", C, face=-1, j=40)], {1: cm.Memory()})
    for on in (False, True):
        cfg = lv.LiveCfg(prio="as", cap_min=0.2, cap_fb=0.2, baseline=on)
        S = lv._Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False, **lv.search_kw(cfg)))
        S.vclock = 0.01
        got[on] = lv._search_one(S, cfg, _snap(sit2), 0, {}, lambda: False)
    assert isinstance(got[True], lv.LivePlan) == isinstance(got[False], lv.LivePlan)
    if isinstance(got[False], lv.LivePlan):
        assert got[True].origin == got[False].origin


def test_switches_default_off():
    c = lv.LiveCfg()
    assert not (c.tube or c.steer or c.midswing or c.swing_hold or c.baseline)
    assert not ms.Cfg().baseline
    assert lv.search_kw(c) == {}
    lv.set_switches(c)
    assert lv.GEO_EXT[0] == 0
    lv.set_switches(lv.LiveCfg(swing_hold=True))
    assert lv.GEO_EXT[0] > 0
    assert lv.search_kw(lv.LiveCfg(baseline=True)) == {"baseline": True, "base_n": 2, "base_last": True}
    assert press.ON[0]


def test_steering_toward_the_path_inside_the_tube(W, p2):
    """LiveCfg.steer (with the tube): her x off the reference path by more than steer_dx while inside the tube - the
    frame's left / right toward the path; no change with a press within +-2 frames or her on the path (P2's plan:
    its jump-left phase)."""
    fx, sit, e = p2
    lv.set_switches(lv.LiveCfg())
    lp = _p2_plan(fx, e)
    o = max(lp.outs, key=lambda o_: o_.p)
    i = lp.outs.index(o)
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", tube=True, steer=True))
    ctl.ctrl, ctl.ctrl_pos = lp, {}
    ctl._tube_kinds = Counter({"tube": 1})
    c = o.cmds
    quiet = [n for n in range(1, min(o.kc, len(c) - 3) - 1)
             if all(((int(c[k]) ^ int(c[k - 1])) & ~lv.DIRS_K) == 0 for k in range(max(n, 1), min(n + 5, len(c))))
             and not any(n <= int(k_) <= n + 14 for (k_, _, _) in o.contacts) and not o.in_block(n + 2)]
    if not quiet:
        pytest.skip("no frame without a press nearby")
    n = quiet[0]
    row: dict = {}
    m0 = int(c[n + 2]) & ~lv.DIRS_K
    her_l = (float(o.pos[n, 0]) - 0.3, float(o.pos[n, 1]))
    assert ctl._steer(lp, [i], i, n, n + 2, her_l, m0, row) & km.B_RIGHT       # left of the path: steer right
    her_r = (float(o.pos[n, 0]) + 0.3, float(o.pos[n, 1]))
    assert ctl._steer(lp, [i], i, n, n + 2, her_r, m0, row) & km.B_LEFT
    her_0 = (float(o.pos[n, 0]) + 0.05, float(o.pos[n, 1]))
    assert ctl._steer(lp, [i], i, n, n + 2, her_0, m0, row) == m0              # within steer_dx: the plan's keys


def test_a_baseline_in_control_bridges_only_base_lead_frames(live_plan):
    """A baseline plan in control: its bridge (the keys the next search starts after) is base_lead frames, not
    ch_lead - a strike found from near now replaces the escape at once."""
    sit, lp0 = live_plan
    lens = {}
    for base in (False, True):
        lp = lv.LivePlan(**{**lp0.__dict__, "outs": list(lp0.outs)})
        lp.base = base
        ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", baseline=True))
        ctl.ctrl, ctl.ctrl_idx = lp, list(range(len(lp.outs)))
        lens[base] = len(ctl._bridge_keys(100)[0])
    assert lens[True] <= lv.LiveCfg().base_lead
    assert lens[False] >= lens[True]
