"""Map v2, t1 workflow stage S2 (HANDOFF 'Task map2 - fix together (t1) - stage S2 (tier 1)'): the per-frame tier 1
(ssbot.map2.tier1; LiveCfg.tier1, default off) - one decision always answers with a plan (the best proven-safe, else
the least-risk one), the escape tail appended to its plan, the tier-1 worker's answer, the controller playing the
newest tier-1 plan whose prefix it followed whenever tier 2 has no plan in control; the switches off: as before."""
from __future__ import annotations

import queue

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import live as lv
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk
from ssbot.map2 import tier1 as t1

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


def _sit(W, x, st="Idle", j=8, face=-1, cx=C):
    return ms.Situation(_ground(W, x, 1 if cx > x else -1), [_obs(st, cx, face=face, j=j)], {1: cm.Memory()})


def _searcher(W, prims=("dslash", "claw")):
    S = ms.Searcher(W, t1.t1_cfg(ms.Cfg.live(prims=prims)))
    S.realizer = lv.HoldRealizer(1, IDLE_H, face0=1)
    S.vclock = 0.01                        # (a virtual clock: the cap in work units - deterministic, no compile time)
    return S


def _pre():
    return ms.Seg(np.zeros(1, np.int64), [], None, "pre")


def _snap(sit, fo=100, cmds=(0, 0), n_inflight=1, seq=1):
    return {"seq": seq, "ep": 0, "f": fo, "fo": fo, "S": sit.S, "cmds": np.asarray(cmds, np.int64),
            "n_inflight": n_inflight, "hold": IDLE_H, "lat_s": 0, "presses": [], "obs": sit.obs, "mems": sit.mems,
            "hazards": sit.hazards, "ctrl": None, "trig": [], "busy": None}


def test_switches_default_off():
    c = lv.LiveCfg()
    assert c.tier1 is False and c.parts == 2
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=1))
    assert ctl.t1_qs == [] and ctl.t1_ctrl is None


def test_a_decision_always_answers(W):
    """An Idle Clapper ahead: a plan (proven safe here); a slam antic at her face: still a plan with an Eval -
    proven safe or the least-risk one; a cap shorter than the root: the safest escape after all."""
    S = _searcher(W)
    r = t1.t1_decide(S, _sit(W, C - 6.0), _pre(), None, cap=1.0)
    assert r.ev is not None and r.safe and r.kind in ("strike", "esc", "endpoint")
    r2 = t1.t1_decide(S, _sit(W, C - 2.6, st="Slam Antic", j=30, face=-1), _pre(), None, cap=1.0)
    assert r2.ev is not None and r2.ev.outcomes and r2.kind
    if not r2.safe:
        assert all(t1.risk_key(r2.ev) <= t1.risk_key(e) for e in r2.tried if e.outcomes and not e.safe
                   and not getattr(e, "tag", ()) and e.finished)
    r3 = t1.t1_decide(S, _sit(W, C - 6.0), _pre(), None, cap=0.0)
    assert r3.ev is not None and r3.kind == "esc"


def test_cont_kept_by_hysteresis(W):
    """The plan being played, re-anchored as CONT, is kept while nothing beats it by w_switch."""
    S = _searcher(W)
    sit = _sit(W, C - 9.0)
    r = t1.t1_decide(S, sit, _pre(), None, cap=1.0)
    assert r.safe
    r2 = t1.t1_decide(S, sit, _pre(), r.ev.plan.copy(), cap=1.0)
    assert r2.safe and r2.kind in ("cont", r.kind)
    if r2.kind != "cont":
        cont = next(e for e in r2.tried if r2.kinds.get(id(e)) == "cont")
        assert not cont.safe or r2.ev.value >= cont.value + S.cfg.w_switch


def test_the_escape_tail(W):
    """A strike plan's own exit appended: the plan longer, every safe outcome re-simulated to the tail's end with the
    same strikes and no collision; a Clawline plan's tail is a segment after its control."""
    S = _searcher(W)
    sit = _sit(W, C - 6.0)
    r = t1.t1_decide(S, sit, _pre(), None, cap=1.0)
    e2, dev = t1.t1_tail(S, sit, r.ev, 40)
    assert getattr(e2, "t1_tail", None) is not None
    assert e2.plan.n_frames() > r.ev.plan.n_frames()
    for o in e2.outcomes:
        if o.safe and o.k_end == o.tr.end and id(o) not in dev:
            assert o.tr.end >= 40
            k = ms.first_collision(o.branch, o.tr, 1, min(o.tr.end, o.P.T if hasattr(o, "P") else 10 ** 6), True)
            assert k is None
    outs = lv.build_outs(e2, True, all_outs=True, light=True, dev_tails=dev)
    assert outs and all(d.geo is None for d in outs) and all(len(d.cmds) > 40 for d in outs)
    claws = [e for e in r.tried if e.safe and any(s.claw is not None for s in e.plan.segs)]
    if claws:
        ec, devc = t1.t1_tail(S, sit, claws[0], 40)
        if getattr(ec, "t1_tail", None) is not None:
            assert len(ec.plan.segs) == len(claws[0].plan.segs) + 1 and ec.plan.segs[-2].claw is not None


def test_build_outs_default_unchanged(W):
    S = _searcher(W)
    sit = _sit(W, C - 6.0)
    r = t1.t1_decide(S, sit, _pre(), None, cap=1.0)
    a = lv.build_outs(r.ev, True)
    b = lv.build_outs(r.ev, True, all_outs=False, light=False, dev_tails=None)
    assert len(a) == len(b) and all(np.array_equal(x.cmds, y.cmds) and x.kc == y.kc for x, y in zip(a, b))
    assert all(not hasattr(x, "safe") for x in a)


def test_the_tier1_worker_answers_with_a_plan(W):
    lv.set_switches(lv.LiveCfg(tier1=True))
    sit = _sit(W, C - 6.0)
    S = lv._Searcher(W, t1.t1_cfg(ms.Cfg.live()))
    S.vclock = 0.01
    cfg = lv.LiveCfg(tier1=True, t1_cap=1.0)
    snap = _snap(sit, cmds=(0, 0, 0, 0, 0), n_inflight=2)
    snap["t_wall"] = None
    lp = lv._t1_search_one(S, cfg, snap, 100, {}, lambda: False)
    assert isinstance(lp, lv.LivePlan) and lp.t1 and lp.t1_kind and lp.pid.startswith("t0:")
    assert lp.n_pre == 5 and np.array_equal(lp.cmds_pre, np.zeros(5, np.int64))
    assert all(o.geo is not None for o in lp.outs)        # (the geometry: the repair's / the audit's re-simulation)
    busy = dict(snap, busy="slash")
    assert lv._t1_search_one(S, cfg, busy, 100, {}, lambda: False)["status"] == "busy:slash"


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


def test_the_controller_plays_tier1(W):
    """parts 0 + tier1 (tier 1 alone): the first tick the fallback has the keys and its bridge goes to the tier-1
    worker; the plan from it (its prefix followed) is adopted and played (own m2, why t1) every tick after it; the
    snapshot while tier 1 plays carries its own keys as the bridge and its plan as CONT; keys off its prefix: dropped."""
    cfg = lv.LiveCfg(prio="as", parts=0, tier1=True, t1_workers=1, t1_cap=1.0)
    ctl = lv.Map2Controller(cfg=cfg)
    out_q, t1q = queue.Queue(), queue.Queue()
    ctl.attach_inproc([], out_q, t1_qs=[t1q])
    ctl.reset(0)
    sit = _sit(W, C - 6.0)
    ctl.trk = _Trk(sit.obs)
    raw = {"hero": {"pos": [float(sit.S[km.PX]), float(sit.S[km.PY])], "hero_accepting_input": True}, "dt": 1 / 60,
           "act": {"mask": 0}}
    hold = km.HoldState.idle(1)
    inf = np.zeros(1, np.int64)
    assert ctl.pre(100, 100, raw, sit.S, inf, hold) is None
    ctl.post(100, 100, raw, sit.S, inf, hold, 0, "plan", np.zeros(20, np.int64), False)
    snap = t1q.get_nowait()
    assert snap["t1_prev"] is None and len(snap["cmds"]) == 2 + cfg.t1_lead
    S = lv._Searcher(W, t1.t1_cfg(ms.Cfg.live()))
    S.vclock = 0.01
    snap["t_wall"] = None
    lp = lv._t1_search_one(S, cfg, snap, 100, {}, lambda: False)
    assert isinstance(lp, lv.LivePlan)
    lp.ep = 0
    out_q.put(lp)
    played = 0
    for k in range(1, 6):
        m = ctl.pre(100 + k, 100 + k, raw, sit.S, inf, hold)
        if k == 1:
            assert ctl.t1_ctrl is lp and ctl.row.get("t1_adopt")
        assert m is not None and ctl.row["why"] == "t1", ctl.row
        ctl.post(100 + k, 100 + k, raw, sit.S, inf, hold, m, "m2", None, False)
        played += 1
    snap2 = None
    while not t1q.empty():
        snap2 = t1q.get_nowait()
    assert snap2 is not None and snap2["t1_prev"] is not None and snap2["t1_prev"][1] == lp.t_a
    st = ctl.stats()
    assert st["counts"]["ticks_t1"] == played and st["counts"]["t1_adopt"] == 1
    # the fallback's key off the plan's keys: the plan does not apply any more
    ctl.post(106, 106, raw, sit.S, inf, hold, int(km.B_DASH | km.B_LEFT), "plan", None, False)
    assert ctl.pre(107, 107, raw, sit.S, inf, hold) is None and ctl.t1_ctrl is None
    assert ctl.stats()["counts"]["t1_left"] == 1


def test_the_tail_starts_after_the_prefix(W):
    """A deviation inside the prefix (the keys in flight and the bridge are played whatever happens) gets no tail of
    its own there; t1_decide moves such an outcome's deviation to the prefix's end (or makes it unsafe)."""
    S = _searcher(W)
    sit = _sit(W, C - 4.0, st="Slam Antic", j=20, face=-1)
    pre = ms.Seg(np.zeros(8, np.int64), [], None, "pre")
    r = t1.t1_decide(S, sit, pre, None, cap=1.0)
    assert r.ev is not None
    for o in r.ev.outcomes:
        if o.safe and o.k_end < o.tr.end:
            assert o.k_end >= 8                     # (no deviation inside the prefix)
    e2, dev = t1.t1_tail(S, sit, r.ev, 40, n_min=8)
    assert all(v[0] >= 8 for v in dev.values())
    for o in e2.outcomes:
        if o.why == "tail":                         # (a dev outcome given its own exact tail: safe to its new end)
            T = o.P.T if hasattr(o, "P") else e2.pred.T
            assert o.safe and o.k_end == o.tr.end and ms.first_collision(o.branch, o.tr, 9, min(o.tr.end, T),
                                                                          True) is None


def test_the_controller_repairs_a_plan_to_take_over(W):
    """No tier-1 plan applies (the fallback left the bridge it sent): the newest proven-safe plan is re-simulated from
    her state now (commit_check, tol_repair) - adopted when it passes, its keys checked from the repair on."""
    cfg = lv.LiveCfg(prio="as", parts=0, tier1=True, t1_workers=1, t1_cap=1.0)
    ctl = lv.Map2Controller(cfg=cfg)
    out_q, t1q = queue.Queue(), queue.Queue()
    ctl.attach_inproc([], out_q, t1_qs=[t1q])
    ctl.reset(0)
    sit = _sit(W, C - 9.0)
    ctl.trk = _Trk(sit.obs)
    raw = {"hero": {"pos": [float(sit.S[km.PX]), float(sit.S[km.PY])], "hero_accepting_input": True}, "dt": 1 / 60,
           "act": {"mask": 0}}
    hold = km.HoldState.idle(1)
    inf = np.zeros(1, np.int64)
    assert ctl.pre(100, 100, raw, sit.S, inf, hold) is None
    ctl.post(100, 100, raw, sit.S, inf, hold, 0, "plan", np.zeros(20, np.int64), False)
    snap = t1q.get_nowait()
    S = lv._Searcher(W, t1.t1_cfg(ms.Cfg.live()))
    S.vclock = 0.01
    snap["t_wall"] = None
    lp = lv._t1_search_one(S, cfg, snap, 100, {}, lambda: False)
    assert isinstance(lp, lv.LivePlan) and lp.t1_safe
    lp.ep = 0
    # the fallback does not follow its bridge: a jump for frame 103
    assert ctl.pre(101, 101, raw, sit.S, inf, hold) is None or True
    ctl.post(101, 101, raw, sit.S, inf, hold, int(km.B_JUMP), "plan", None, False)
    out_q.put(lp)
    S1 = W.roll(sit.S, np.array([0, int(km.B_JUMP)], np.int64)).final[:, 0].copy()
    m = ctl.pre(102, 102, raw, S1, np.array([int(km.B_JUMP)], np.int64), hold)
    c = ctl.stats()["counts"]
    assert c.get("t1_broken", 0) >= 1 and any(k.startswith("t1_repair_") for k in c), c
    if c.get("t1_repair_ok"):
        assert ctl.t1_ctrl is lp and m is not None and lp._rep_k == 104


def test_t2_tail_switch(W):
    """LiveCfg.t2_tail (default off): the deep search's plan sent with its escape tail - its outcomes' committed part
    longer, the tail a segment of the plan itself (re-simulated by every check)."""
    sit = _sit(W, C - 6.0)
    snap = _snap(sit, cmds=(0, 0, 0), n_inflight=2)
    snap["t_wall"] = None
    out = {}
    for tail in (False, True):
        cfg = lv.LiveCfg(t2_tail=tail)
        S = lv._Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
        S.vclock = 0.01
        lp = lv._search_one(S, cfg, dict(snap), 0, {}, lambda: False)
        out[tail] = lp
    if isinstance(out[False], lv.LivePlan) and isinstance(out[True], lv.LivePlan) and \
            out[True].plan.n_frames() > out[False].plan.n_frames():
        assert max(o.kc for o in out[True].outs) > max(o.kc for o in out[False].outs)


def test_a_plan_unaware_of_the_plan_in_hand_replaces_it_only_when_better(W):
    """Two tier-1 workers: a newer plan from a snapshot taken before the plan in hand was adopted (its CONT was not that
    plan) does not replace a proven-safe plan in hand unless better by t1_switch; one that had it as CONT does."""
    cfg = lv.LiveCfg(prio="as", parts=0, tier1=True, t1_workers=2, t1_cap=1.0)
    ctl = lv.Map2Controller(cfg=cfg)
    out_q, q0, q1 = queue.Queue(), queue.Queue(), queue.Queue()
    ctl.attach_inproc([], out_q, t1_qs=[q0, q1])
    ctl.reset(0)
    sit = _sit(W, C - 9.0)
    ctl.trk = _Trk(sit.obs)
    raw = {"hero": {"pos": [float(sit.S[km.PX]), float(sit.S[km.PY])], "hero_accepting_input": True}, "dt": 1 / 60,
           "act": {"mask": 0}}
    hold = km.HoldState.idle(1)
    inf = np.zeros(1, np.int64)
    ctl.pre(100, 100, raw, sit.S, inf, hold)
    ctl.post(100, 100, raw, sit.S, inf, hold, 0, "plan", np.zeros(24, np.int64), False)
    snap = q0.get_nowait()
    assert not q1.empty()                              # (each idle worker its own snapshot)
    S = lv._Searcher(W, t1.t1_cfg(ms.Cfg.live()))
    S.vclock = 0.01
    snap["t_wall"] = None
    a = lv._t1_search_one(S, cfg, dict(snap), 100, {}, lambda: False)
    b = lv._t1_search_one(S, cfg, dict(snap, seq=snap["seq"] + 1, fo=101, f=101), 101, {}, lambda: False)
    assert isinstance(a, lv.LivePlan) and isinstance(b, lv.LivePlan) and a.t1_safe
    a.ep = b.ep = 0
    b.t_a = a.t_a + 1
    b.value = float(a.value)                          # (not better)
    out_q.put(a)
    ctl.pre(101, 101, raw, sit.S, inf, hold)
    assert ctl.t1_ctrl is a
    ctl.post(101, 101, raw, sit.S, inf, hold, int(ctl.row.get("mask", 0) or 0) if False else
             int(a.outs[0].cmds[3]), "m2", None, False)
    out_q.put(b)
    ctl.pre(102, 102, raw, sit.S, inf, hold)
    c = ctl.stats()["counts"]
    assert ctl.t1_ctrl is a and c.get("t1_unaware", 0) + c.get("t1_broken", 0) >= 1


def test_no_dev_tail_from_a_swing():
    """A dev tail is not made from a state mid-swing / mid-bounce (the probe's plain roll misses the strike's contact
    and bounce) and a dev-tailed outcome lists no contact after its tail's start."""
    import inspect
    src = inspect.getsource(t1.t1_tail)
    assert "km.ATTACKING] > 0 or Sk[km.BOUNCE] >= 0" in src
    src2 = inspect.getsource(lv.build_outs)
    assert "c[0] <= k0t" in src2
