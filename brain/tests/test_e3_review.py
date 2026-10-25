"""Map v2 stage E3 (HANDOFF 'Task map2 - the evaluation and the handover - stage E3'): the two verifiers' findings on
E1 / E2, each fix behind a switch default off - the swing from her observed state (swing_fix: the tracker's down
slash ATK_PDIR, a hooked Clawline's forced bounce, a slash out of the air sprint), the tube's keep at her observed
offset (tube_fix: the vertical band, the drift, a contact ahead, the circles, the outcomes shifted in a block), the
swing hold (hold_fix: a hit ends it, no hold after an unsafe verdict, re-validated every tick; its keys audited), the
oracle's late apply (late_act), the witness's retry (witness_retry)."""
from __future__ import annotations

import pickle
import queue
from pathlib import Path

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import live as lv
from ssbot.map2 import press
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

R, L, J, A, D, DS = km.B_RIGHT, km.B_LEFT, km.B_JUMP, km.B_ATTACK, km.B_DOWN, km.B_DASH
SW = ("ON", "SIDE", "FREE_POGO", "SHRINK", "SIDE_RULE", "SIDE_LAG", "XVX_MIN")
P2_FIXTURE = Path(r"C:\ssbot\data\m2_play\map2\ev\e2\gate\p2_fixture.pkl")


@pytest.fixture(scope="module")
def W():
    return ms.World()


@pytest.fixture(autouse=True)
def _switches():
    saved = {k: getattr(press, k)[0] for k in SW}
    lv.set_switches(lv.LiveCfg())
    yield
    lv.set_switches(lv.LiveCfg())
    for k, v in saved.items():
        getattr(press, k)[0] = v


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


def _out(kc: int, pos: np.ndarray, boxes: list, circles: list | None = None) -> lv.OutData:
    """A synthetic outcome: one body box per frame (boxes[k] or none), circles [(k, cx, cy, r)]."""
    o = lv.OutData()
    nf = kc + 1
    off = np.zeros(nf + 1, np.int64)
    rows = []
    for k in range(nf):
        b = boxes[k] if k < len(boxes) else None
        if b is not None:
            rows.append(b)
        off[k + 1] = len(rows)
    BX = np.asarray(rows, float).reshape(-1, 4)
    coff = np.zeros(nf + 1, np.int64)
    CO = []
    for k in range(nf):
        for (kk, cx, cy, r) in (circles or ()):
            if kk == k:
                CO.append((cx, cy, r))
        coff[k + 1] = len(CO)
    o.geo = (off, BX, np.ones(len(BX), np.int64), coff, np.asarray(CO, float).reshape(-1, 3))
    o.kc, o.end, o.pos = kc, kc, pos
    o.contacts, o.segs, o.blocks, o.rare, o.boxes, o.presses = [], [], [], {}, {}, []
    o.recs, o.vrecs = {}, {}
    o.kcol = None
    return o


# ---- tube_fix: the vertical band, the drift (findings evaluation 1, 2; handover 9) ----------------------------------

def test_the_tube_tests_her_observed_height_offset():
    """A body box 0.15 u below her planned feet / above her head, her y 0.18 u off toward it: E2's corridor (her
    hurtbox +- 0.1 u) keeps the plan, her real hurtbox meets the box - tube_keep (the offset applied, the band grown
    by eps(k)) does not; the same offset away from the box is kept."""
    hw, hh, hdy = cm.HURTBOX
    kc, y = 30, 20.0
    pos = np.tile(np.array([[30.0, y]]), (kc + 1, 1))
    foot, top = y + hdy - hh, y + hdy + hh
    cfg = lv.LiveCfg()
    for box, dy in (((29.0, foot - 2.0, 31.0, foot - 0.15), -0.18), ((29.0, top + 0.15, 31.0, top + 3.0), 0.18)):
        o = _out(kc, pos, [box] * (kc + 1))
        dlo, dhi = lv.tube_window(lv.tube_corridor(o, pos, 1), pos, 5, cfg.tube_dx)
        assert dlo <= 0.0 <= dhi                                         # E2: kept
        tr = lv.tube_rows(o, pos, 1)
        assert not lv.tube_keep(tr, 5, 0.0, dy, 0.0, 0.0, cfg.tube_vh, cfg.tube_dx, cfg.cor_dy)
        far = (box[0], box[1] + 3.0, box[2], box[3] + 3.0) if dy > 0 else (box[0], box[1] - 3.0, box[2], box[3] - 3.0)
        o2 = _out(kc, pos, [far] * (kc + 1))
        assert lv.tube_keep(lv.tube_rows(o2, pos, 1), 5, 0.0, dy, 0.0, 0.0, cfg.tube_vh, cfg.tube_dx, cfg.cor_dy)


def test_the_tube_extrapolates_her_drift():
    """A body ahead of her path at her height from frame 9 on (beyond her x 0.1 u off plus eps(k) to the plan's end):
    her offset is kept while it holds; the same offset growing since the previous tick (a velocity off the path's - a
    key a frame late) is not."""
    hw, hh, hdy = cm.HURTBOX
    cfg = lv.LiveCfg()
    kc, n = 12, 5
    e = lv.eps_x(np.arange(0, kc - n + 1))
    gap = 0.1 + float(e[kc - n]) + 0.05
    rx = (0.5 - 0.1) / cfg.tube_vh - 0.005                              # (inside the cap)
    assert 0.1 + rx * cfg.tube_vh + float(e[cfg.tube_vh]) > gap
    pos = np.zeros((kc + 1, 2))
    pos[:, 0] = 30.0
    pos[:, 1] = 20.0
    boxes = [None] * 9 + [(30.0 + hw + gap, 19.0, 32.0, 23.0)] * (kc - 8)
    o = _out(kc, pos, boxes)
    tr = lv.tube_rows(o, pos, 1)
    assert lv.tube_keep(tr, n, 0.1, 0.0, 0.0, 0.0, cfg.tube_vh, cfg.tube_dx, cfg.cor_dy)
    assert not lv.tube_keep(tr, n, 0.1, 0.0, rx, 0.0, cfg.tube_vh, cfg.tube_dx, cfg.cor_dy)


def test_the_circles_stay_on_both_timings():
    """A rune bomb already lit (frames 10 .. 15, world-fixed) and a Clapper shifted 2 frames from frame 4: E2 moved
    the bomb with the Clapper (frames 10, 11 lost); tube_fix keeps the rows on the planned and the shifted timing."""
    kc = 30
    pos = np.tile(np.array([[30.0, 20.0]]), (kc + 1, 1))
    circ = [(k, 40.0, 4.0, 2.0) for k in range(10, 16)]
    o = _out(kc, pos, [(50.0, 0.0, 51.0, 3.0)] * (kc + 1), circ)
    o.recs = {1: (np.array([0]), np.array([0]), np.array([0]), np.array([0]), np.array([50.0]), np.array([1]))}
    o.vrecs = {1: (np.array([0]), np.array([0]), np.array([0]), np.array([50.0]), np.array([1]))}

    def lit(c):
        coff = c.geo[3]
        return {k for k in range(len(coff) - 1) if coff[k + 1] > coff[k]}
    lv.set_switches(lv.LiveCfg())
    c0 = lv.shift_outcome(o, {1: (2, 4)})
    assert 10 not in lit(c0) and 11 not in lit(c0)                      # E2: moved with the Clapper
    lv.set_switches(lv.LiveCfg(tube_fix=True))
    c1 = lv.shift_outcome(o, {1: (2, 4)})
    assert set(range(10, 18)) <= lit(c1)                                # both timings


def test_two_clappers_shifted_end_by_the_earliest():
    """Two Clappers shifted differently: the committed end follows the earliest (E2: whichever came first)."""
    kc = 30
    pos = np.tile(np.array([[30.0, 20.0]]), (kc + 1, 1))
    o = _out(kc, pos, [None] * (kc + 1))
    o.end = 40
    lv.set_switches(lv.LiveCfg(tube_fix=True))
    c = lv.shift_outcome(o, {1: (3, 5), 2: (-1, 5)})
    assert c.kc == kc - 1
    o.kcol = 33
    c = lv.shift_outcome(o, {1: (3, 5), 2: (-1, 5)})
    assert (c.kc, c.kcol) == (kc - 1, 32)


# ---- the gate's P2 fixture: the tracker's down slash (findings handover 1, 4, 5) -----------------------------------

@pytest.fixture(scope="module")
def p2(W):
    if not P2_FIXTURE.exists():
        pytest.skip("the gate's P2 fixture is not on this machine")
    with open(P2_FIXTURE, "rb") as fh:
        fx = pickle.load(fh)
    sit = ms.Situation(fx["S"], list(fx["obs"]), dict(fx["mems"]), list(fx["hazards"]))
    plan = ms.Plan([ms.Seg(np.asarray(fx["masks"], np.int64), list(fx["dsl"]), None, "gate")], "prim")
    S = ms.Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
    e = S.ev.evaluate(sit, plan)
    return fx, sit, e


def _p2_plan(fx, e):
    return lv.LivePlan(pid="p2", t_a=int(fx["t_a"]), outs=lv.build_outs(e), plan=e.plan, n_pre=int(fx["n_pre"]),
                       ms=0.0, ep=0, S_a=np.asarray(fx["S"], float).reshape(km.K, -1)[:, 0].copy(),
                       hold_a=fx["hold"], lat_a=int(fx["lat_s"]), claw_lock=-99)


def _raw(fr, n, clip="DownSlashAlt"):
    return {"hero": {"pos": fr[n]["her"], "hero_accepting_input": True, "anim": {"clip": clip}}, "dt": 1 / 60,
            "act": {"mask": int(fr[n]["lat"])}}


def test_the_trackers_down_slash_is_the_models(W, p2):
    """The gate's P2 frames 16 - 24 (the tracker's states mid down slash): ATK_PDIR 0, no swing - map2's copy of the
    state (swing_fix: her clip DownSlash*) has ATK_PDIR 2 / ATK_KIND 0, the swing is carried; the re-check from the
    recorded state at frame 20 of an outcome with its contact at 23: 'danger' without (the contact never credited),
    ok with it."""
    fx, sit, e = p2
    fr = fx["frames"]
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", swing_fix=True))
    ctl.reset(0)
    n = 20
    S = np.asarray(fr[n]["S"], float).reshape(km.K, -1)[:, 0]
    assert S[km.ATTACKING] > 0 and S[km.ATK_PDIR] == 0.0
    assert ms.swing_from_state(S, [1], W.params.frame_time) is None
    Sm, swc = ctl._mstate(S, int(fx["t_a"]) + n, _raw(fr, n))
    assert Sm[km.ATK_PDIR] == 2.0 and Sm[km.ATK_KIND] == 0.0 and swc == {"pogo": True, "spr": False}
    assert S[km.ATK_PDIR] == 0.0                                       # (a copy)
    assert ms.swing_from_state(Sm, [1], W.params.frame_time, **swc) is not None
    lp = _p2_plan(fx, e)
    early = [i for i, o in enumerate(lp.outs) if any(c[0] == 23 for c in o.contacts)]
    infl = np.array([int(fr[n + 1]["act"])], np.int64)
    cfg = lv.LiveCfg(prio="as", midswing=True)
    args = (W, lp, int(fx["t_a"]) + n)
    rest = (infl, fr[n]["hold"], int(fr[n]["lat"]), fr[n]["her"], fr[n]["obs"], cfg)
    r0 = lv.commit_check(*args, S, *rest, idx=early[:1], tol=1e9)
    r1 = lv.commit_check(*args, Sm, *rest, idx=early[:1], tol=1e9, swc=swc)
    assert not r0[0] and r0[1] == "danger", r0[:2]
    assert r1[0], r1[:2]


def test_a_hooked_clawlines_bounce_carries_no_pogo_iframes(W):
    """A bounce whose onset is a Clawline's control (the forced bounce of a hook) carries no pogo i-frames
    (swing_fix: pogo False); a bounce begun later (a pogo after the hook) does."""
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", swing_fix=True))
    ctl.reset(0)
    ctl._claw_P, ctl._claw_ctl = 1000, 1026
    S = km.initial_state(W.params, 30.0, 12.0, ground=False)
    S[km.BOUNCE] = 1.0
    _, swc = ctl._mstate(S, 1027, {"hero": {"anim": {"clip": "DownSpikeBounce 1"}}})
    assert swc["pogo"] is False
    assert ms.swing_from_state(S, [1], W.params.frame_time) == (0, (), 7)
    assert ms.swing_from_state(S, [1], W.params.frame_time, **swc) is None
    _, swc2 = ctl._mstate(S, 1040, {"hero": {"anim": {"clip": "DownSpikeBounce 1"}}})
    assert swc2["pogo"] is True


def test_a_carried_slash_out_of_the_air_sprint_keeps_the_side_rule(W):
    """S1's case (an air dash -> sprint, a down slash out of it beside a body): the press path gives the body's
    contact ('side_spr'); the same slash carried in from mid-swing (search.simulate's swing) gave a pogo (E2) - with
    the slash marked out of the sprint (swing_fix: spr) it gives the body's contact too."""
    press.ON[0] = press.SIDE[0] = True
    S = km.initial_state(W.params, 30.0, 8.0, ground=False, facing=1)
    S[km.VY] = 0.0
    m = np.array([DS | R] * 5 + [DS | R | D | A] + [DS | R | D] * 6 + [R] * 10, np.int64)
    kt = press.trace(W, S, m)
    ts, kind = press.ds_start(kt, 6)
    assert kind == "down"
    r = W.roll(S, m)
    x, y = r.pos[0, ts + 4]
    bb = float(r.box[0, ts + 4, 1])
    box = (x + 0.4, bb + 1.0 - 3.0, x + 1.4, bb + 1.0)
    T = 60

    def bx(iid):
        b = np.full((T, 4), np.nan)
        b[:] = box
        return b
    tr = ms.simulate(W, ms.Plan([ms.Seg(m, [(5, 1)])]), bx, 1, S, sk.HOOK_VARIANTS[0])
    assert not tr.contacts and tr.bad and tr.bad[0][1] == "side_spr"
    k = ts + 1
    S_k, _ = ms.state_at(W, tr, k)
    assert S_k[km.ATK_PDIR] == 2.0
    for spr, side in ((False, False), (True, True)):
        sw = ms.swing_from_state(S_k, [1], W.params.frame_time, spr=spr)
        assert sw is not None and (len(sw) > 3) == spr
        tr2 = ms.simulate(W, ms.Plan([ms.Seg(m[k:].copy(), [])]), lambda iid: bx(iid)[k:], 1, S_k,
                          sk.HOOK_VARIANTS[0], swing=sw)
        if side:
            assert not tr2.contacts and tr2.bad and tr2.bad[0][1] == "side_spr"
        else:
            assert tr2.contacts                                          # E2's carry: a pogo


# ---- hold_fix (findings handover 6, 7, 8) ----------------------------------------------------------------------------

def _p2_ctl(W, fx, e, cfg):
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
    ctl._run = {"lp": lp, "fo": int(fx["t_a"]) + n_c, "f": int(fx["t_a"]) + n_c, "S0": fr[n_c]["S"],
                "inflight": np.array([int(fr[n_c + 1]["act"])], np.int64), "hold": fr[n_c]["hold"],
                "lat_s": int(fr[n_c]["lat"])}
    return ctl, n_c


def _p2_ticks(ctl, fx, n0, n_end, hit_at=None, bounce_from=None):
    """The controller over P2's recorded frames n0 .. n_end - 1; hit_at: her hit on that frame; bounce_from: her
    state bouncing from that frame on (the recording's hero did not pogo: the fallback jumped)."""
    fr = fx["frames"]
    whys = []
    for n in range(n0, n_end):
        if n not in fr or n + 1 not in fr:
            break
        f = int(fx["t_a"]) + n
        raw = _raw(fr, n, "Airborne")
        ctl.trk = _Trk(fr[n]["obs"])
        ctl._fo_prev = f - 1
        if hit_at is not None and n == hit_at:
            ctl.last_hit = f
        S = np.array(fr[n]["S"], float, copy=True)
        if bounce_from is not None and n >= bounce_from:
            S.reshape(km.K, -1)[km.BOUNCE, 0] = 0.0
        hs = km.HoldState(*(np.asarray(x)[None] for x in fr[n]["hold"]))
        infl = np.array([int(fr[n + 1]["act"])], np.int64)
        m = ctl.pre(f, f, raw, S, infl, hs)
        whys.append((n, ctl.row.get("why")))
        own = "m2" if m is not None else "plan"
        ctl.post(f, f, raw, S, infl, hs, int(m) if m is not None else 0, own, None, False)
    return whys


def test_a_hit_ends_the_swing_hold(W, p2):
    """P2 with the tube and the swing hold: the plan ends mid-swing, the hold takes the keys; a hit then - E2 resumed
    the hold on the next tick (its keys until its end), hold_fix ends it."""
    fx, sit, e = p2
    base = dict(prio="as", parts=1, log=True, replay=True, tube=True, midswing=True, swing_hold=True)
    for fix in (False, True):
        ctl, n_c = _p2_ctl(W, fx, e, lv.LiveCfg(**base, hold_fix=fix))
        whys = _p2_ticks(ctl, fx, n_c, 32)
        sw = [n for (n, w) in whys if w == "swing"]
        assert sw, whys[-6:]
        ctl2, _ = _p2_ctl(W, fx, e, lv.LiveCfg(**base, hold_fix=fix))
        whys2 = _p2_ticks(ctl2, fx, n_c, 32, hit_at=sw[0] + 1, bounce_from=sw[0])
        after = [w for (n, w) in whys2 if n >= sw[0] + 3]
        assert ("swing" in after) == (not fix), (fix, whys2[-8:])


def test_no_hold_after_an_unsafe_verdict(W, p2):
    """The plan dropped mid-swing on the tube's exact verdict 'danger' (or a newer search's 'unsafe'): E2 started the
    hold (its check from the commit's base), hold_fix does not; a drop on the Clappers' timing still holds."""
    fx, sit, e = p2
    fr = fx["frames"]
    base = dict(prio="as", parts=1, log=True, replay=True, tube=True, midswing=True, swing_hold=True)
    n = 20
    for fix in (False, True):
        for why, want in (("tube_danger", not fix), ("unsafe", not fix), ("clappers", True)):
            ctl, n_c = _p2_ctl(W, fx, e, lv.LiveCfg(**base, hold_fix=fix))
            _p2_ticks(ctl, fx, n_c, n)
            assert ctl.ctrl is not None
            ctl._obs_last = fr[n]["obs"]
            ctl._drop(why)
            assert (ctl._hold_sw is not None) == want, (fix, why)


def test_the_holds_keys_are_audited(W, p2):
    """audit_runs: the hold's keys (sent after the plan ended) are re-simulated with the run's (E2 audited none)."""
    fx, sit, e = p2
    cfg = lv.LiveCfg(prio="as", parts=1, log=True, replay=True, tube=True, midswing=True, swing_hold=True,
                     audit_runs=True)
    ctl, n_c = _p2_ctl(W, fx, e, cfg)
    whys = _p2_ticks(ctl, fx, n_c, 36)
    assert any(w == "swing" for (_, w) in whys)
    assert ctl.ep_c.get("audit_hold_runs", 0) >= 1, (dict(ctl.ep_c), whys[-6:])
    assert ctl.ep_c.get("audit_hold_col", 0) == 0


# ---- tube_fix: the outcomes shifted in a Clawline's block (finding handover 7) --------------------------------------

def test_outcomes_shifted_in_a_block_are_rechecked_out_of_it(W, p2):
    """An outcome marked shifted without a re-check: out of the block the tube re-checks it exactly (no 'sync' /
    'tube' keep) - tube_fix; E2 kept it."""
    fx, sit, e = p2
    fr = fx["frames"]
    for fix in (False, True):
        ctl, n_c = _p2_ctl(W, fx, e, lv.LiveCfg(prio="as", parts=1, log=True, replay=True, tube=True, midswing=True,
                                                 tube_fix=fix))
        ctl._tube_unchk = {0}
        _p2_ticks(ctl, fx, n_c, n_c + 1)
        assert (ctl.ep_c.get("tube_unchk_recheck", 0) > 0) == fix


# ---- late_act (finding handover 10) ----------------------------------------------------------------------------------

def test_the_oracles_late_apply_is_seen(W, p2):
    """Her latched keys at the observation frame against the keys sent through the hold filter from the previous
    tick's state: equal - nothing; the jump sent for this frame not latched (the oracle a frame late) - late_act."""
    fx, sit, e = p2
    fr = fx["frames"]
    ctl, n_c = _p2_ctl(W, fx, e, lv.LiveCfg(prio="as", parts=1, log=True, late_act=True))
    hold0 = lv.hold_tuple(km.HoldState.idle(1))
    ctl._hold_prev = (1000, hold0)
    ctl.sent_hist[1001] = int(J)
    exp = ctl._exp_lat(1001)
    assert exp == int(lv.hold_filter1(np.array([J], np.int64), hold0)[-1]) and exp & J
    ctl.sent_hist[1001] = 0
    assert ctl._exp_lat(1001) == 0
    assert ctl._exp_lat(1006) is None                                   # no tick within 3 frames


# ---- witness_retry (finding evaluation 5) ----------------------------------------------------------------------------

def test_the_witness_retry_switch(W):
    S = ms.Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False))
    assert S._wit_retry() is None
    S = ms.Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False, witness_fast=True, witness_retry=True))
    assert S._wit_retry() == (0.01, ms.WITNESS_TOL)
    S = ms.Searcher(W, ms.Cfg.live(fwd_threads=0, pass2_bg=False, witness_retry=True))
    assert S._wit_retry() is None                                       # (only with witness_fast)
    assert lv.search_kw(lv.LiveCfg(witness_retry=True)) == {"witness_retry": True}


def test_the_e3_switches_default_off():
    c = lv.LiveCfg()
    assert not (c.swing_fix or c.tube_fix or c.hold_fix or c.late_act or c.witness_retry)
    assert not ms.Cfg().witness_retry
    lv.set_switches(c)
    assert lv.TUBE_FIX[0] is False
    assert lv.search_kw(c) == {}
