"""Map v2 stage M4c: the search played live (ssbot.map2.live, SSBOT_FORUM_MAP2) - the hold filter, the realizer, the
root prefix, the plans' command timelines, the exact commit check, the controller's commit / execute / hand-over, and
that the bot imports ssbot.map2 only with the switch on."""
from __future__ import annotations

import importlib
import os
import queue
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import live as lv
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

C = 33.0


@pytest.fixture(scope="module")
def W():
    return ms.World()


def _obs(st, x, face=-1, j=2, iid=1):
    return cm.Obs(iid, st, j / 60.0, x, cm.STAND_Y, 0.0, 0.0, face, 230, None, will_evade=None, j=j)


def _ground(W, x, face=1):
    return km.initial_state(W.params, x, sk.FLOOR + sk.FOOT, ground=True, facing=face)


IDLE_H = lv.hold_tuple(km.HoldState.idle(1))


def test_hold_filter1_matches_kinematics():
    rng = np.random.default_rng(3)
    for trial in range(200):
        T = int(rng.integers(1, 50))
        cur, m = 0, np.zeros(T, np.int64)
        for t in range(T):
            if rng.random() < 0.45:
                cur ^= 1 << int(rng.choice([0, 1, 2, 4, 18, 19, 20, 21]))
            m[t] = cur
        h = km.HoldState.idle(1)
        if trial % 2:
            _, h = km.hold_filter(rng.integers(0, 1 << 22, 3), h)
        a, h_a = km.hold_filter(m, h)
        b, h_b = lv.hold_run(m, lv.hold_tuple(h))
        assert np.array_equal(a, b)
        assert np.array_equal(h_a.latched[0], h_b[0]) and np.array_equal(h_a.pending[0], h_b[2])


def test_realizer_latches_presses_two_frames():
    """A one-frame dash press is latched for two frames; a down slash press keeps its frame; the prefix is kept."""
    R, D = km.B_RIGHT, km.B_DASH
    m = np.array([0, 0, R | D, R, R, 0, 0, lv.M_DS, 0, 0], np.int64)
    plan = ms.Plan([ms.Seg(m, [(7, 5)], None, "x")])
    rl = lv.HoldRealizer(2, IDLE_H)
    p2 = rl(plan)
    lat = p2.segs[0].masks
    assert [ms.key_str(x) for x in lat[2:5]] == ["RS", "RS", "R"]
    assert p2.segs[0].dsl == [(7, 5)] and lat[7] & lv.M_DS == lv.M_DS and lat[8] & km.B_ATTACK
    # a press whose key was released one frame before it: the filter delays it (moved) or takes it away
    m2 = np.array([0, lv.M_DS, 0, lv.M_DS, 0, 0, 0], np.int64)
    p3 = lv.HoldRealizer(0, IDLE_H)(ms.Plan([ms.Seg(m2, [(1, 5), (3, 5)], None, "y")]))
    assert p3.segs[0].dsl[0] == (1, 5)
    assert len(p3.segs[0].dsl) == 1 or p3.segs[0].dsl[1][0] > 3


def test_outcome_cmds_clawline_and_block():
    class T:
        pass
    tr = T()
    s0 = ms.Seg(np.array([km.B_RIGHT] * 5, np.int64), [], (1, 7), "c")
    s1 = ms.Seg(np.array([0, km.B_LEFT, km.B_LEFT], np.int64), [], None, "after")
    tr.segs, tr.seg_start, tr.end = [s0, s1], [0, 30], 33
    c = lv.outcome_cmds(tr)
    assert list(c[1:5]) == [km.B_RIGHT] * 4
    assert all(c[k] == lv.M_CLAW | km.B_RIGHT for k in (5, 6, 7))       # P = 5 (the last mask frame) .. P + 2
    assert not c[8:31].any() and list(c[31:34]) == [0, km.B_LEFT, km.B_LEFT]


def test_root_prefix_plans_start_with_it(W):
    """decide(prefix=...): every plan starts with the prefix's masks; the noop is the prefix and one frame."""
    sit = ms.Situation(_ground(W, C - 7.0), [_obs("Idle", C, face=-1, j=8)], {1: cm.Memory()})
    pre = ms.Seg(np.full(4, km.B_RIGHT, np.int64), [], None, "pre")
    S = ms.Searcher(W, ms.Cfg(depth=1, cap_s=2.0))
    r = S.decide(sit, prefix=pre)
    assert r.ev is not None
    for e in r.tried:
        if e.plan.segs:
            assert list(e.plan.segs[0].masks[:4]) == [km.B_RIGHT] * 4
    rt = S.root(sit, pre)
    assert rt.k0 == 4 and list(rt.noop_ev.plan.segs[0].masks) == [km.B_RIGHT] * 4 + [0]


def _snap(sit, fo=100, cmds=(0, 0), n_inflight=1, seq=1, ctrl=None):
    return {"seq": seq, "ep": 0, "f": fo, "fo": fo, "S": sit.S, "cmds": np.asarray(cmds, np.int64),
            "n_inflight": n_inflight, "hold": IDLE_H, "lat_s": 0, "presses": [], "obs": sit.obs, "mems": sit.mems,
            "hazards": sit.hazards, "ctrl": ctrl, "trig": [], "busy": None}


@pytest.fixture(scope="module")
def live_plan(W):
    """A LivePlan from a forced situation: her 7 u from an Idle Clapper, its face toward her."""
    sit = ms.Situation(_ground(W, C - 7.0), [_obs("Idle", C, face=-1, j=8)], {1: cm.Memory()})
    S = lv._Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
    cfg = lv.LiveCfg(prio="as", cap_min=1.5, cap_fb=1.5)
    lp = lv._search_one(S, cfg, _snap(sit), 0, {}, lambda: False)
    assert isinstance(lp, lv.LivePlan), lp
    return sit, lp


def test_commit_check_exact_and_rejections(W, live_plan):
    sit, lp = live_plan
    cfg = lv.LiveCfg(prio="as")
    o0 = max(lp.outs, key=lambda o: o.p)
    infl = np.array([o0.cmds[1]], np.int64)
    her = (float(sit.S[km.PX]), float(sit.S[km.PY]))
    ok, why, info = lv.commit_check(W, lp, 100, sit.S, infl, IDLE_H, 0, her, sit.obs, cfg)
    assert ok, (why, info)
    assert info["dev"] <= 1e-6 and set(info["alive"]) and info["pos_over"]
    # her 0.6 u elsewhere: the re-simulated path leaves the planned one
    S2 = sit.S.copy()
    for i in (km.PX, km.QX, km.SX):
        S2[i] += 0.6
    assert lv.commit_check(W, lp, 100, S2, infl, IDLE_H, 0, (her[0] + 0.6, her[1]), sit.obs, cfg)[1] == "path"
    # the Clapper 1 u elsewhere: no outcome is consistent
    ob = [_obs("Idle", C + 1.0, face=-1, j=8)]
    assert lv.commit_check(W, lp, 100, sit.S, infl, IDLE_H, 0, her, ob, cfg)[1] == "clappers"
    # a slash of the fallback's in flight that the plan does not have
    bad = np.array([lv.M_DS], np.int64)
    ok3, why3, _ = lv.commit_check(W, lp, 100, sit.S, bad, IDLE_H, 0, her, sit.obs, cfg)
    assert not ok3 and why3 in ("unplanned slash", "path", "danger", "press moved")
    # a plan from the future of this observation
    assert lv.commit_check(W, lp, 99, sit.S, infl, IDLE_H, 0, her, sit.obs, cfg)[1] == "future"


class _Trk:
    """A Clapper tracker stand-in (the controller's obs)."""

    def __init__(self, obs):
        self.o = obs
        self.cl = {o.iid: {"st": o.st, "ent": 0, "e": {}} for o in obs}

    def obs(self):
        return self.o

    def mems(self):
        return {o.iid: cm.Memory() for o in self.o}

    def hazards(self, K):
        return []


def _obs_at(o, n):
    """The Clappers of an outcome at frame n as Obs (its records)."""
    inv = {v: k for k, v in o.sids.items()}
    out = []
    for iid, (ks, st, j, x, f) in o.recs.items():
        a = int(np.searchsorted(ks, n))
        if a < len(ks) and ks[a] == n:
            out.append(cm.Obs(iid, inv[int(st[a])], float(j[a]) / 60.0, float(x[a]), cm.STAND_Y, 0.0, 0.0, int(f[a]),
                              230, None, j=int(j[a])))
    return out


def test_controller_commit_execute_handover(W, live_plan):
    sit, lp = live_plan
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=1, log=True))
    out_q, in_q = queue.Queue(), queue.Queue()
    ctl.attach_inproc([in_q], out_q)
    ctl.reset(0)
    ctl.trk = _Trk(sit.obs)
    lp.ep = 0
    out_q.put(lp)
    o0 = max(lp.outs, key=lambda o: o.p)
    raw = {"hero": {"pos": [float(sit.S[km.PX]), float(sit.S[km.PY])], "hero_accepting_input": True}, "dt": 1 / 60,
           "act": {"mask": 0}}
    hold = km.HoldState.idle(1)
    m = ctl.pre(100, 100, raw, sit.S, np.array([o0.cmds[1]], np.int64), hold)
    assert ctl.took and ctl.ctrl is lp and m is not None
    ctl.post(100, 100, raw, sit.S, np.array([o0.cmds[1]], np.int64), hold, m, "m2", None, False)
    snap = in_q.get_nowait()
    assert snap["ctrl"] == (lp.pid, 100) and snap.get("plan_obj") is not None
    assert len(snap["cmds"]) > snap["n_inflight"]                     # the bridge: the plan's own keys
    # the next frames along the plan: map2 keeps the keys (the most probable consistent outcome's commands)
    kept = 0
    for n in (1, 2, 3):
        i_best = None
        raw["hero"]["pos"] = [float(o0.pos[n, 0]), float(o0.pos[n, 1])]
        ctl.trk = _Trk(_obs_at(o0, n))
        m = ctl.pre(100 + n, 100 + n, raw, sit.S, np.array([o0.cmds[n + 1]], np.int64), hold)
        assert m is not None, ctl.row
        kept += 1
        ctl.post(100 + n, 100 + n, raw, sit.S, np.array([o0.cmds[n + 1]], np.int64), hold, m, "m2", None, False)
    # her 1 u off the plan: the per-frame check fails, the fallback has the keys
    raw["hero"]["pos"] = [float(o0.pos[4, 0]) + 1.0, float(o0.pos[4, 1])]
    ctl.trk = _Trk(_obs_at(o0, 4))
    assert ctl.pre(104, 104, raw, sit.S, np.array([0], np.int64), hold) is None
    assert ctl.ctrl is None and ctl.row["why"] == "fail:hero"
    ctl.post(104, 104, raw, sit.S, np.array([0], np.int64), hold, 0, "plan", None, False)
    st = ctl.stats()
    assert st["counts"]["commits"] == 1 and st["counts"]["ticks_m2"] == 4 and st["counts"]["drop_hero"] == 1


def test_bot_imports_map2_only_with_the_switch():
    """SSBOT_FORUM_MAP2 unset: importing the policy does not import ssbot.map2 (a fresh interpreter); the policy
    imports ssbot.map2.live only inside its switch."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SSBOT_FORUM_MAP2")}
    code = ("import sys, ssbot.train.forum_planner_policy as p; "
            "print('MAP2', p.MAP2, any(m.startswith('ssbot.map2') for m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                         cwd=str(Path(lv.__file__).resolve().parents[2]), timeout=600)
    assert "MAP2 False False" in out.stdout, out.stdout + out.stderr
    src = Path(importlib.import_module("ssbot.train.forum_planner_policy").__file__).read_text(encoding="utf-8")
    lines = [ln for ln in src.splitlines() if re.search(r"(from|import)\s+ssbot\.map2", ln)]
    assert lines == ["            from ssbot.map2 import live as m2live"]
