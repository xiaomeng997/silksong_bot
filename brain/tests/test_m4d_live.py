"""Map v2 stage M4d: the review findings on the live map (ssbot.map2.live) - the timing views and the end of a possible
outcome's committed part, the hook variants told apart by her control and the keys of disagreeing outcomes, the
bridge, the Clawline's direction latched at its press and the Clawline presses a plan does not have, a freeze or a hit
between two ticks, a newer search's verdict on the plan in control, the Cogfly throw's keys, the bot side's exceptions,
the per-episode stats, the workers' exit with the bot."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import live as lv
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

C = 33.0
SID = {"Idle": 3, "Slam Antic": 7}
HER = (20.0, 4.57)
R, L, J = km.B_RIGHT, km.B_LEFT, km.B_JUMP
IDLE_H = lv.hold_tuple(km.HoldState.idle(1))


class _Trk:
    def __init__(self, obs):
        self.o = obs
        self.cl = {o.iid: {"st": o.st, "ent": 0, "e": {}} for o in obs}

    def obs(self):
        return self.o

    def feed(self, raw, g):
        pass

    def mems(self):
        return {o.iid: cm.Memory() for o in self.o}

    def hazards(self, K):
        return []


def _timeline(shift_from: int, shift: int, T: int = 70, slam_at: int = 30) -> list:
    """(frame, state, j) of one Clapper: Idle j = k, Slam Antic from slam_at (nominal); records from shift_from on
    drawn shift frames later."""
    out = []
    for k in range(T):
        st, j = ("Idle", k) if k < slam_at else ("Slam Antic", k - slam_at)
        out.append((k + (shift if k >= shift_from else 0), st, j))
    return out


def _out(p, kc, end, cmds, view, base_spread=(26, 4), blocks=(), ctrls=(), why="", kcol=None, variant="early",
         base=None):
    o = lv.OutData()
    o.p, o.kc, o.end = float(p), int(kc), int(end)
    c = np.zeros(end + 1, np.int64)
    c[1:] = np.asarray(cmds, np.int64)[:end]
    o.cmds = c
    o.pos = np.tile(np.array(HER, float), (kc + 1, 1))
    o.sids = dict(SID)
    vk = np.array([k for (k, _, _) in view if k <= kc], np.int64)
    vs = np.array([SID[s] for (k, s, _) in view if k <= kc], np.int64)
    vj = np.array([j for (k, _, j) in view if k <= kc], np.int64)
    o.vrecs = {1: (vk, vs, vj, np.full(len(vk), C), np.full(len(vk), -1))}
    k0, sp = base_spread
    base = _timeline(10 ** 9, 0) if base is None else base
    lo = np.array([k for (k, _, _) in base], np.int64)
    hi = lo + np.where(lo >= k0, sp, 0)
    keep = lo <= kc
    o.recs = {1: (lo[keep], hi[keep], np.array([SID[s] for (_, s, _) in base], np.int64)[keep],
                  np.array([j for (_, _, j) in base], np.int64)[keep], np.full(int(keep.sum()), C),
                  np.full(int(keep.sum()), -1))}
    o.segs, o.presses, o.variant, o.boxes, o.geo, o.rare = [], [], variant, {}, None, {}
    o.rare_k, o.label, o.contacts = np.zeros(0, np.int64), "", []
    o.blocks, o.ctrls, o.why, o.kcol = list(blocks), list(ctrls), why, kcol
    return o


def _obs(view, n):
    for (k, st, j) in view:
        if k == n:
            return [cm.Obs(1, st, j / 60.0, C, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=j)]
    return []


def _ctl(outs, **kw):
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=1, log=True, **kw))
    ctl.attach_inproc([], queue.Queue())
    ctl.reset(0)
    lp = lv.LivePlan(pid="t", t_a=0, outs=outs, ms=0.0, plan=None, value=1.0)
    ctl.ctrl, ctl.ctrl_idx, ctl.ctrl_pos = lp, list(range(len(outs))), {}
    return ctl


def _drive(ctl, view, n_max, acc_fn=lambda n: True, first=0, n0=0):
    """Ticks on time (f = fo = n, from n0): the Clapper as the truth's view, her position the plan's; {frame: key
    sent}, the stop (n, why)."""
    S0 = np.zeros(km.K)
    hold = km.HoldState.idle(1)
    sent = {k: v for k, v in ctl.sent_hist.items()} if n0 else {1: first}
    if not n0:
        ctl.sent_hist[1] = first
        ctl.own_hist[1] = "m2"
    for n in range(n0, n_max):
        raw = {"hero": {"pos": list(HER), "hero_accepting_input": acc_fn(n)}, "dt": 1 / 60, "act": {"mask": 0}}
        ctl.trk = _Trk(_obs(view, n))
        ctl.feed(raw, n)
        infl = np.array([sent.get(n + 1, 0)], np.int64)
        m = ctl.pre(n, n, raw, S0, infl, hold)
        if m is None:
            return sent, (n, ctl.row.get("why"))
        sent[n + 2] = int(m)
        ctl.post(n, n, raw, S0, infl, hold, int(m), "m2", None, False)
    return sent, None


@pytest.fixture(scope="module")
def views():
    early = _timeline(26, 0)
    late = _timeline(26, 4)
    cm_ = [R] * 80
    # the early view must deviate at its reveal + lag (44: a collision at 49 follows); the late one runs to 61
    oe = _out(0.5, 44, 61, cm_, early, why="dev", kcol=49)
    ol = _out(0.5, 61, 61, cm_, late)
    return early, late, oe, ol


def test_timing_views_end_at_a_possible_views_deviation(views):
    """Finding timing 1 / safety 1: the two timing views of a branch match the spread records together, so M4c ran on
    with the late view's keys past the early view's deviation into its collision; M4d ends the plan there."""
    early, late, oe, ol = views
    sent, stop = _drive(_ctl([oe, ol]), early, 60)
    assert max(sent) == 44 and stop == (43, "end")
    # M4c's rule (documents the defect): the late view's keys at 45 .. 49, into the early view's collision at 49
    sent_c, _ = _drive(_ctl([oe, ol], views_exact=False, ctl_check=False, dis_hold=False), early, 60)
    assert max(sent_c) >= 49
    # the late view seen (the early one contradicted at its slam frame 30): its keys to its own end
    sent_l, stop_l = _drive(_ctl([oe, ol]), late, 70)
    assert max(sent_l) == 61 and stop_l[1] == "end"
    # a timing between the views (2 frames late): both contradicted - all consistent ones count, it ends at 44
    mid = _timeline(26, 2)
    sent_m, stop_m = _drive(_ctl([oe, ol]), mid, 60)
    assert max(sent_m) == 44 and stop_m[1] == "end"


def test_commit_check_rejects_a_plan_whose_possible_view_ended(views):
    """The same rule at the commit: a consistent, possible outcome whose committed part ends before the frame being
    chosen rejects the plan ('ended'); the contradicted view does not."""
    early, late, oe, ol = views
    lp = lv.LivePlan(pid="t", t_a=0, outs=[oe, ol], ms=0.0)
    cfg = lv.LiveCfg(prio="as")
    W = None                                       # not reached: rejected before the re-simulation
    ok, why, _ = lv.commit_check(W, lp, 44, np.zeros(km.K), np.array([R], np.int64), IDLE_H, 0, HER,
                                 _obs(early, 44), cfg)
    assert not ok and why == "ended"
    assert lv.possible(lp, [0, 1], 34, _obs(late, 34), cfg) == [1]           # early contradicted (slam vs Idle)


def _variant_outs():
    """Two hook variants after a Clawline pressed at 20: control 40 (early) / 43 (late); each presses jump 2 frames
    after its control."""
    ce, cl = 40, 43
    view = [(k, "Idle", k) for k in range(90)]
    c_e = [R] * 19 + [lv.M_CLAW | R] * 3 + [0] * 18 + [0, J, J] + [R] * 40
    c_l = [R] * 19 + [lv.M_CLAW | R] * 3 + [0] * 21 + [0, J, J] + [R] * 40
    oe = _out(0.25, 80, 80, c_e, view, base_spread=(10 ** 6, 0), blocks=[(20, ce)], ctrls=[(20, ce)], variant="early",
              base=view)
    ol = _out(0.25, 80, 80, c_l, view, base_spread=(10 ** 6, 0), blocks=[(20, cl)], ctrls=[(20, cl)], variant="late",
              base=view)
    return view, oe, ol, ce, cl


def test_hook_variants_told_apart_by_control_no_unplanned_press():
    """Findings timing 2 / safety 4: after a hook the variants' keys differ around control; M4c sent the most
    probable one's (the early jump during the late pull: queued to its control). M4d: her control tells them apart
    (the early variant contradicted when she has none at 41, the late one when she has it at 40), a key the
    possible ones disagree on is not pressed."""
    view, oe, ol, ce, cl = _variant_outs()
    # truth late: no jump before the late one's (45), then its keys
    sent, _ = _drive(_ctl([oe, ol]), view, 70, acc_fn=lambda n: not (20 <= n < cl))
    jumps = [k for k in sorted(sent) if sent[k] & J and not (sent.get(k - 1, 0) & J)]
    assert jumps and jumps[0] == cl + 2
    # truth early: the late variant contradicted at 40 (control seen), the early keys from then on
    sent_e, _ = _drive(_ctl([oe, ol]), view, 70, acc_fn=lambda n: not (20 <= n < ce))
    assert all(sent_e[k] == int(oe.cmds[k]) for k in sent_e if k >= ce + 2 and k <= 80)
    # M4c's rule: the early jump at 42 during the late pull
    sent_c, _ = _drive(_ctl([oe, ol], views_exact=False, ctl_check=False, dis_hold=False), view, 70,
                       acc_fn=lambda n: not (20 <= n < cl))
    assert sent_c[ce + 2] & J


def test_bridge_from_the_possible_outcomes():
    """Finding timing 8: the bridge (the keys expected while the next search runs) is the possible outcomes' agreed
    keys - after control the seen variant's, not the most probable of all."""
    view, oe, ol, ce, cl = _variant_outs()
    oe.p = 0.4                                     # the early one the more probable
    ol.p = 0.1
    ctl = _ctl([oe, ol])
    _drive(ctl, view, cl + 2, acc_fn=lambda n: not (20 <= n < cl))
    f = cl + 1
    b, _ = ctl._bridge_keys(f)
    assert b and b == [int(ol.cmds[k]) for k in range(f + 3, f + 3 + len(b))]


def test_realizer_latches_the_clawline_direction_at_its_press():
    """Findings timing 3 / safety 3: masks ending [R, L, R] with a Clawline toward +1 - M4c's realizer left L latched
    at P (the game throws toward her facing: away); now the press moves until R latches with it at P."""
    m = np.array([R, R, R, R, L, R], np.int64)
    after = ms.Seg(np.zeros(3, np.int64), [], None, "after")
    plan = ms.Plan([ms.Seg(m, [], (1, 7), "c"), after])
    rl = lv.HoldRealizer(0, IDLE_H)
    p2 = rl(plan)
    s0 = p2.segs[0]

    class T:
        pass
    tr = T()
    P = len(s0.masks)
    tr.segs, tr.seg_start, tr.end = [s0, after], [0, P + 25], P + 28
    c = lv.outcome_cmds(tr)
    lat = lv.hold_filter1(c[1:], IDLE_H)
    mp = int(lat[P - 1])
    assert mp & lv.M_CLAW and mp & R and not (mp & L)
    assert not (int(lat[P - 2]) & lv.M_CLAW) and rl.n_claw_shift == 1 and P == len(m) + 1
    # M4c's realizer at the same masks: L latched at P
    lat_old, _ = lv.hold_run(np.concatenate([m[:5], [lv.M_CLAW | R] * 3]), IDLE_H)
    assert int(lat_old[5]) & L
    # no direction latched at P while she already faces the target: the press stays (the game keeps her facing)
    m2 = np.array([R, R, R, R, 0, R], np.int64)
    rl2 = lv.HoldRealizer(0, IDLE_H, face0=1)
    s2 = rl2(ms.Plan([ms.Seg(m2, [], (1, 7), "c"), after])).segs[0]
    assert len(s2.masks) == len(m2) and rl2.n_claw_shift == 0 and not (int(s2.masks[-1]) & R)
    # ... facing away (an L tap before): moved until R latches
    m3 = np.array([0, 0, 0, 0, L, R], np.int64)
    rl3 = lv.HoldRealizer(0, IDLE_H, face0=1)
    s3 = rl3(ms.Plan([ms.Seg(m3, [], (1, 7), "c"), after])).segs[0]
    assert rl3.n_claw_shift == 1 and int(s3.masks[-1]) & R


@pytest.fixture(scope="module")
def W():
    return ms.World()


@pytest.fixture(scope="module")
def live_plan(W):
    sit = ms.Situation(km.initial_state(W.params, C - 7.0, sk.FLOOR + sk.FOOT, ground=True, facing=1),
                       [cm.Obs(1, "Idle", 8 / 60.0, C, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=8)], {1: cm.Memory()})
    S = lv._Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
    S.vclock = 0.002                               # the cap in work units (a busy machine: the same plan)
    cfg = lv.LiveCfg(prio="as", cap_min=1.5, cap_fb=1.5)
    snap = {"seq": 1, "ep": 0, "f": 100, "fo": 100, "S": sit.S, "cmds": np.zeros(2, np.int64), "n_inflight": 1,
            "hold": IDLE_H, "lat_s": 0, "presses": [], "obs": sit.obs, "mems": sit.mems, "hazards": sit.hazards,
            "ctrl": None, "trig": [], "busy": None}
    lp = lv._search_one(S, cfg, snap, 0, {}, lambda: False)
    assert isinstance(lp, lv.LivePlan), lp
    return sit, lp


def test_commit_check_rejects_a_clawline_it_does_not_have(W, live_plan):
    """Findings timing 4 / safety 2: a Clawline press in flight (the fallback's script) or latched now is not in the
    plan's re-simulation - rejected ('unplanned Clawline', 'in a Clawline'); a slash still is."""
    sit, lp = live_plan
    cfg = lv.LiveCfg(prio="as")
    o0 = max(lp.outs, key=lambda o: o.p)
    her = (float(sit.S[km.PX]), float(sit.S[km.PY]))
    c1 = int(o0.cmds[1])
    assert lv.commit_check(W, lp, 100, sit.S, np.array([c1], np.int64), IDLE_H, 0, her, sit.obs, cfg)[0]
    for infl in (c1 | lv.M_CLAW | R, (c1 & ~R) | lv.M_CLAW | L, c1 | lv.M_CLAW):
        ok, why, _ = lv.commit_check(W, lp, 100, sit.S, np.array([infl], np.int64), IDLE_H, 0, her, sit.obs, cfg)
        assert not ok and why == "unplanned Clawline", why
    ok, why, _ = lv.commit_check(W, lp, 100, sit.S, np.array([c1], np.int64),
                                 lv.hold_run(np.array([lv.M_CLAW], np.int64), IDLE_H)[1], lv.M_CLAW, her, sit.obs, cfg)
    assert not ok and why == "in a Clawline"


def test_no_commit_without_control(W, live_plan):
    """Finding timing 4: pre() commits nothing while she has no control (a Clawline under way, a stun)."""
    sit, lp = live_plan
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=1))
    out_q = queue.Queue()
    ctl.attach_inproc([], out_q)
    ctl.reset(0)
    ctl.trk = _Trk(sit.obs)
    lp.ep = 0
    out_q.put(lp)
    o0 = max(lp.outs, key=lambda o: o.p)
    raw = {"hero": {"pos": [float(sit.S[km.PX]), float(sit.S[km.PY])], "hero_accepting_input": False},
           "dt": 1 / 60, "act": {"mask": 0}}
    assert ctl.pre(100, 100, raw, sit.S, np.array([o0.cmds[1]], np.int64), km.HoldState.idle(1)) is None
    assert ctl.ctrl is None and ctl.pending and ctl.ep_c["commit_wait_noinput"] == 1
    raw["hero"]["hero_accepting_input"] = True
    assert ctl.pre(100, 100, raw, sit.S, np.array([o0.cmds[1]], np.int64), km.HoldState.idle(1)) is not None


def test_freeze_or_hit_between_ticks_drops_the_plan(views):
    """Findings timing 5 / safety 7: a freeze (or its slow-time ramp) or her hit on a frame whose tick was skipped
    drops the plan in control on the next tick (M4c checked only the observed frame's dt; the hit after the freeze);
    the hit is counted by who sent the keys at its frame."""
    early, late, oe, ol = views
    S0, hold = np.zeros(km.K), km.HoldState.idle(1)
    for kind, raw_skip in (("freeze", {"dt": 0.0}), ("freeze", {"dt": 0.33 / 60}),
                           ("hit", {"dt": 1 / 60, "ev": [{"k": "damage"}]})):
        ctl = _ctl([oe, ol])
        sent, _ = _drive(ctl, early, 10)
        ctl.feed({"hero": {"pos": list(HER)}, "act": {"mask": 0}, **raw_skip}, 10)      # tick 10 skipped
        raw = {"hero": {"pos": list(HER), "hero_accepting_input": True}, "dt": 1 / 60, "act": {"mask": 0}}
        ctl.trk = _Trk(_obs(early, 11))
        ctl.feed(raw, 11)
        assert ctl.pre(11, 11, raw, S0, np.array([R], np.int64), hold) is None
        assert ctl.row["why"] == kind and ctl.ep_c["drop_" + kind] == 1
        if kind == "hit":
            assert ctl.ep_c["hit_m2"] == 1 and ctl.ep_c["hits"] == 1


def test_newer_search_verdict_drops_or_cuts_the_plan(views):
    """Findings timing 6 / safety 5: a worker that evaluated the plan in control from a newer snapshot as UNSAFE
    (status 'unsafe' / 'noop', or a plan, with prev_safe False): dropped at once; cut after that search's bridge
    when its noop (the bridge, then stop) was safe. M4c only counted it."""
    early, late, oe, ol = views
    for noop_safe in (False, True):
        ctl = _ctl([oe, ol])
        _drive(ctl, late, 5)
        ctl.out_q.put({"kind": "status", "status": "noop" if noop_safe else "unsafe", "ep": 0, "seq": 1, "fo": 3,
                       "n_pre": 12, "ctrl_seen": "t", "had_prev": True, "prev_safe": False, "noop_safe": noop_safe})
        sent2, stop = _drive(ctl, late, 40, n0=5)
        if not noop_safe:
            assert stop == (5, "unsafe") and ctl.ctrl is None and ctl.ep_c["drop_unsafe"] == 1
        else:
            assert max(sent2) == 3 + 12 and stop == (14, "cut")
    # a verdict with prev_safe True (or on another plan) changes nothing
    ctl = _ctl([oe, ol])
    ctl.out_q.put({"kind": "status", "status": "kept", "ep": 0, "seq": 1, "fo": 3, "n_pre": 12, "ctrl_seen": "t",
                   "had_prev": True, "prev_safe": True})
    sent, stop = _drive(ctl, late, 70)
    assert max(sent) == 61


def test_cogfly_keys_not_in_flight_for_the_model(views):
    """Finding timing 7: the Cogfly throw's Up + QuickCast (stripped in the policy's prefix on its frames) stay out
    of map2's keys in flight, the hold state and the snapshots (the kinematics would cast)."""
    early, late, oe, ol = views
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=1))
    inq = queue.Queue()
    ctl.attach_inproc([inq], queue.Queue())
    ctl.reset(0)
    ctl.trk = _Trk(_obs(early, 5))
    S0, hold = np.zeros(km.K), km.HoldState.idle(1)
    raw = {"hero": {"pos": list(HER), "hero_accepting_input": True}, "dt": 1 / 60, "act": {"mask": 0}}
    for f in (4, 5):
        ctl.pre(f, f, raw, S0, np.array([0], np.int64), hold)
        ctl.post(f, f, raw, S0, np.array([0], np.int64), hold, lv.COG, "cog", None, False)
    infl = ctl._eff_inflight(5, 6, np.array([0, 0], np.int64))
    assert not any(int(x) & lv.COG for x in infl)
    _, hold_cog = km.hold_filter(np.array([lv.COG, lv.COG], np.int64), km.HoldState.idle(1))
    lat, des, pen, age = ctl._hold_clean(lv.hold_tuple(hold_cog), 6)
    assert not any(lat[b] for b in lv._COG_BITS)
    snaps = []
    while not inq.empty():
        snaps.append(inq.get_nowait())
    snaps = [s for s in snaps if not s.get("note")]
    assert snaps and not any(int(x) & lv.COG for s in snaps for x in s["cmds"])


def test_bot_side_exceptions_fall_back(views):
    """Finding robustness 5: an exception in pre / post / feed hands the keys to the fallback (None) and is logged;
    after err_max in an episode map2 is off for the rest of it."""
    early, late, oe, ol = views
    ctl = _ctl([oe, ol], err_max=2)

    class Bad(_Trk):
        def obs(self):
            raise ValueError("boom")

        def feed(self, raw, g):
            raise IndexError("boom")
    ctl.trk = Bad([])
    raw = {"hero": {"pos": list(HER), "hero_accepting_input": True}, "dt": 1 / 60, "act": {"mask": 0}}
    S0, hold = np.zeros(km.K), km.HoldState.idle(1)
    ctl.feed(raw, 1)
    assert ctl.pre(1, 1, raw, S0, np.array([0], np.int64), hold) is None and ctl.ctrl is None
    ctl.post(1, 1, raw, S0, np.array([0], np.int64), hold, 0, "plan", None, False)
    assert ctl.disabled and ctl.ep_c["errors_pre"] == 1 and ctl.ep_c["errors_feed"] == 1
    assert ctl.pre(2, 2, raw, S0, np.array([0], np.int64), hold) is None and ctl.row["why"] == "off"
    ctl.reset(1)
    assert not ctl.disabled


def test_stats_per_episode(views):
    """Finding robustness 4: stats() is per episode (an attempt row is one episode), the run's in run_counts."""
    early, late, oe, ol = views
    ctl = _ctl([oe, ol])
    _drive(ctl, late, 20)
    a = ctl.stats()
    ctl.reset(1)
    ctl.ctrl, ctl.ctrl_idx = lv.LivePlan(pid="u", t_a=0, outs=[oe, ol], ms=0.0), [0, 1]
    _drive(ctl, late, 10)
    b = ctl.stats()
    assert a["counts"]["ticks"] == 20 and b["counts"]["ticks"] == 10 and b["run_counts"]["ticks"] == 30
    assert b["ep"] == 1 and b["episode"]["ep"] == 1


_REPO_BRAIN = Path(lv.__file__).resolve().parents[2]


def _py(code: str, timeout: float) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True,
                          cwd=str(_REPO_BRAIN), env=env, timeout=timeout)


def test_workers_exit_with_the_bot():
    """Finding robustness 1: a worker whose bot process died outright (no exit handlers) exits by itself."""
    code = """
        import os, sys
        from ssbot.map2 import live as lv
        ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=1, warm_rec=0, ready_s=600))
        ctl.start(wait=True)
        print("PID", ctl.ready[0]["os_pid"], ctl.ready[0]["boost"], flush=True)
        os._exit(0)
    """
    out = _py(code, 600)
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("PID")]
    assert line, out.stdout + out.stderr[-2000:]
    assert "bg " in line[0]                        # finding robustness 3: the background pass thread's numba threads
    pid = int(line[0].split()[1])
    import psutil
    t0 = time.time()
    while psutil.pid_exists(pid) and time.time() - t0 < 20:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                break
        except psutil.NoSuchProcess:
            break
        time.sleep(0.5)
    alive = psutil.pid_exists(pid)
    if alive:
        try:
            alive = "multiprocessing" in " ".join(psutil.Process(pid).cmdline())
        except psutil.Error:
            alive = False
    if alive:
        psutil.Process(pid).kill()
    assert not alive, "the worker outlived its bot"


def test_bot_exit_does_not_hang_on_a_dead_workers_queue():
    """Finding robustness 2: notes queued to a worker that stopped reading (dead) never block the bot's exit."""
    code = """
        import os, sys
        from ssbot.map2 import live as lv
        ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=1, warm_rec=0, ready_s=600))
        ctl.start(wait=True)
        p = ctl.procs[0]
        p.terminate(); p.join(10)
        for i in range(40):
            ctl.in_qs[0].put({"note": True, "ep": 0, "ctrl": None, "trig": [], "pad": "x" * 2000})
        print("EXITING", flush=True)
    """
    out = _py(code, 600)                          # (M4c: hung here - the feeder thread joined at exit)
    assert "EXITING" in out.stdout, out.stdout + out.stderr[-2000:]
    assert out.returncode == 0
