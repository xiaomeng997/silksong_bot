"""Map v2 stage M4d2 (HANDOFF 'Task map2 - stage M4' / 'M4d2'): the map in control - the fallback planner follows the
bridge it sent while map2 searches from it (its CONTINUE row = that bridge, first among its safe rows), a break cuts
the search, the parts of one decision get one snapshot, a plan waits for its root, a strike pressed right after the
bridge is not 'too short', the noop's alternative, a plan REPAIRED from the keys actually sent - and the reveal
latency (a Clapper's move start sends the newest snapshot with the short bridge to every worker, their searches cut)."""
from __future__ import annotations

import queue
from types import SimpleNamespace

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import live as lv
from ssbot.map2 import search as ms
from ssbot.map2 import strike as sk

C = 33.0
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


class _Flag:
    def __init__(self, v=1):
        self.value = v


def _obs(st="Idle", j=8, iid=1):
    return [cm.Obs(iid, st, j / 60.0, C, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=j)]


def _raw(acc=True, clip="Idle"):
    return {"hero": {"pos": [26.0, 4.57], "hero_accepting_input": acc, "anim": {"clip": clip}}, "dt": 1 / 60,
            "act": {"mask": 0}}


def _ctl(n=2, **kw):
    ctl = lv.Map2Controller(cfg=lv.LiveCfg(prio="as", parts=n, **kw))
    qs = [queue.Queue() for _ in range(n)]
    idles = [_Flag(1) for _ in range(n)]
    ctl.attach_inproc(qs, queue.Queue(), idles)
    ctl.reset(0)
    ctl.trk = _Trk(_obs())
    return ctl, qs, idles


def _snaps(q):
    out = []
    while True:
        try:
            x = q.get_nowait()
        except queue.Empty:
            return out
        out.append(x)


def _post(ctl, f, mask, own="plan", res_cmd=None, raw=None):
    S0 = np.zeros(km.K)
    ctl.row = {"f": int(f), "fo": int(f)}
    ctl.post(f, f, raw or _raw(), S0, np.array([0], np.int64), km.HoldState.idle(1), int(mask), own, res_cmd, False)


def test_short_fix_keeps_a_strike_pressed_right_after_the_bridge():
    """M4d sent a strike pressed 1 - 3 frames after its prefix as 'noop' (min_frames 4): the search's best on 63 of
    the 84 noop answers in the w7 scan had a safe alternative, 8 of them strikes with a hit."""
    n_pre = 18
    m = np.zeros(n_pre + 2, np.int64)
    m[n_pre + 1] = km.B_DOWN | km.B_ATTACK
    strike = SimpleNamespace(plan=ms.Plan([ms.Seg(m, [(n_pre + 1, 7)], None, "s")]))
    stand = SimpleNamespace(plan=ms.Plan([ms.Seg(np.zeros(n_pre + 2, np.int64), [], None, "s")]))
    assert not lv._short(strike, n_pre, lv.LiveCfg())
    assert lv._short(strike, n_pre, lv.LiveCfg(short_fix=False))
    assert lv._short(stand, n_pre, lv.LiveCfg())


def test_one_snapshot_per_decision_and_the_held_bridge():
    """sync: a snapshot only when every worker is idle, the same one to each (the two parts of one decision); the
    planner's bridge is held while a part has not answered (hold_row: its plan from f + 2, aligned by the frames
    elapsed); a key off it breaks the hold and cuts the search (a note with 'cut'); a broken bridge is not held."""
    ctl, qs, idles = _ctl()
    res_cmd = np.array([R] * 6 + [L] * 30, np.int64)
    _post(ctl, 100, R, res_cmd=res_cmd)
    s0 = [[x for x in _snaps(q) if not x.get("note")] for q in qs]
    assert len(s0[0]) == 1 and len(s0[1]) == 1 and s0[0][0]["seq"] == s0[1][0]["seq"] == 0
    snap = s0[0][0]
    assert list(snap["cmds"][snap["n_inflight"]:]) == list(res_cmd[1:1 + ctl.cfg.fb_lead])
    assert snap["t_wall"] > 0 and not snap["rev"]
    # one part answered, the other still searching: no new snapshot, the bridge held
    ctl._answered(0, 0)
    idles[0].value = 1
    idles[1].value = 0
    row = ctl.hold_row(101)
    assert row is not None and list(row[:6]) == list(res_cmd[1:7]) and ctl._hold == (0, R)
    _post(ctl, 101, int(row[0]), res_cmd=row)
    assert not [x for q in qs for x in _snaps(q) if not x.get("note")]
    assert ctl.ep_c["hold_followed"] == 1
    # two ticks later (a skipped frame): aligned by the frames
    row = ctl.hold_row(103)
    assert list(row[:4]) == list(res_cmd[3:7])
    # the planner leaves it (its own check): the search is cut, the bridge no longer held
    _post(ctl, 103, L, res_cmd=np.array([L] * 30, np.int64))
    notes = [x for q in qs for x in _snaps(q) if x.get("note")]
    assert notes and all(n_.get("cut") == 0 for n_ in notes)
    assert ctl.ep_c["hold_broken"] == 1 and ctl.snaps_out[0]["broken"]
    assert ctl.hold_row(104) is None
    # map2 in control: never held
    ctl2, _, _ = _ctl()
    _post(ctl2, 100, R, res_cmd=res_cmd)
    ctl2.ctrl = SimpleNamespace(pid="x", t_a=0)
    assert ctl2.hold_row(101) is None


def test_a_move_start_sends_the_newest_snapshot_with_the_short_bridge_at_once():
    """rev_cut: a Clapper's move start (Idle -> Slam Antic) sends the newest snapshot to every worker, busy or not,
    with the short bridge (rev_lead) and cut = the older snapshots (the workers' readers abort those searches)."""
    ctl, qs, idles = _ctl()
    res_cmd = np.array([R] * 30, np.int64)
    ctl._triggers(100, _obs("Idle", 8))
    _post(ctl, 100, R, res_cmd=res_cmd)
    _snaps(qs[0])
    _snaps(qs[1])
    idles[0].value = idles[1].value = 0              # both searching
    ctl.trk = _Trk(_obs("Slam Antic", 0))
    ctl.row = {}
    ctl._triggers(101, ctl.trk.obs())
    assert ctl.rev_new is not None
    _post(ctl, 101, R, res_cmd=res_cmd)
    got = [[x for x in _snaps(q) if not x.get("note")] for q in qs]
    assert len(got[0]) == 1 and len(got[1]) == 1
    s1 = got[0][0]
    assert s1["rev"] and s1["cut"] == s1["seq"] - 1 and len(s1["cmds"]) - s1["n_inflight"] == ctl.cfg.rev_lead
    assert ctl.rev_new is None and ctl.ep_c["rev_sent"] == 1 and ctl.rev_log
    # a state change that is not a move start (Slam Antic -> Slam 0) does not
    ctl.trk = _Trk(_obs("Slam 0", 0))
    ctl._triggers(102, ctl.trk.obs())
    assert ctl.rev_new is None


def test_a_plan_waits_for_its_decisions_other_part_until_its_root():
    ctl, qs, idles = _ctl()
    _post(ctl, 100, R, res_cmd=np.array([R] * 30, np.int64))
    lp = SimpleNamespace(seq=0, t_a=100, n_pre=19)
    assert not ctl._ready(lp, 101)                   # part 1 still searching, the root at 120
    assert ctl._ready(lp, 117)                       # its root due: checked
    ctl._answered(0, 0)
    ctl._answered(0, 1)
    assert ctl._ready(lp, 101)                       # both parts answered


def test_no_input_in_the_hero_models_own_states():
    """noinput_kin: 'no input' in the umbrella / the sprint (the hero model's states) is not busy; a Clawline's pull,
    the roar lock are."""
    ctl, _, _ = _ctl()
    assert ctl._busy(100, _raw(acc=False, clip="Umbrella Inflate")) is None
    assert ctl._busy(100, _raw(acc=False, clip="Roar Lock")) == "no input"
    ctl2, _, _ = _ctl(noinput_kin=False)
    assert ctl2._busy(100, _raw(acc=False, clip="Umbrella Inflate")) == "no input"


@pytest.fixture(scope="module")
def W():
    return ms.World()


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
        lp = sent[-1]                                 # (its final answer was the anytime plan already sent)
    return sit, lp, sent


def test_anytime_plans_go_out_while_the_search_runs(live_plan):
    sit, lp, sent = live_plan
    assert sent and all(isinstance(x, lv.LivePlan) and not x.final for x in sent)
    assert all(x.seq == 1 and x.t_a == 100 for x in sent)
    vals = [x.value for x in sent]
    assert vals == sorted(vals)                      # each one better than the one before


def test_repair_from_the_keys_actually_sent(W, live_plan):
    """repair (the strict replay): her anchor state with the keys actually sent since the anchor, then the plan's
    own commands - the bridge as planned: ok (its own path); a slash the plan does not have: rejected; the bridge's
    direction flipped for 4 frames (her path ~1.3 u off): rejected on the path."""
    sit, lp, _ = live_plan
    cfg = lv.LiveCfg(prio="as", tol_repair=0.3)
    o0 = max(lp.outs, key=lambda o: o.p)
    her = (float(sit.S[km.PX]), float(sit.S[km.PY]))
    f = 104                                          # keys for 101 .. 105 sent
    keys = np.array([int(o0.cmds[k]) for k in range(1, f + 2 - 100)], np.int64)
    obs3 = [cm.Obs(1, "Idle", 11 / 60.0, C, cm.STAND_Y, 0.0, 0.0, -1, 230, None, j=11)]     # the Clapper at 103
    ok, why, info = lv.repair_check(W, lp, 103, f, keys, her, obs3, cfg)
    assert ok, (why, info)
    assert info["dev"] < 1e-6
    bad = keys.copy()
    bad[2] |= km.B_ATTACK
    ok, why, _ = lv.repair_check(W, lp, 103, f, bad, her, obs3, cfg)
    assert not ok and why == "unplanned slash"
    flip = np.array([L] * len(keys), np.int64)
    ok, why, info = lv.repair_check(W, lp, 103, f, flip, her, obs3, cfg)
    assert not ok and why in ("path", "press moved", "claw latch"), why


def test_alt_over_the_noop(monkeypatch):
    """alt_noop: the search's best is the noop (the fallback's bridge, then stop) - its best safe non-noop plan within
    alt_slack is sent instead; none within it: 'noop'."""
    made = []
    monkeypatch.setattr(lv, "_live_plan", lambda S, e, *a, **k: made.append(e) or SimpleNamespace(e=e))
    pre = ms.Seg(np.zeros(3, np.int64), [], None, "pre")
    pre.hold_after = IDLE_H
    monkeypatch.setattr(lv, "build_prefix", lambda snap: (pre, ""))

    def ev(origin, value, n=60):
        return SimpleNamespace(plan=ms.Plan([ms.Seg(np.zeros(n, np.int64), [], None, origin)], origin), safe=True,
                               finished=True, value=value, tag=(), hits=0.0, p_safe=1.0)
    noop = ev("noop", -0.05, 4)

    class _S:
        cfg = ms.Cfg()
        realizer = None
        on_best = None
        abort_fn = None

        def __init__(self, tried):
            self.tried = tried

        def decide(self, sit, prev=None, cap_s=None, prefix=None):
            return SimpleNamespace(ev=noop, tried=self.tried, kept=False, n_cand=len(self.tried), timed_out=False)
    snap = {"seq": 3, "ep": 0, "f": 10, "fo": 10, "S": np.zeros(km.K), "n_inflight": 1, "obs": _obs(), "mems": {},
            "hazards": [], "ctrl": None, "busy": None, "cmds": np.zeros(3, np.int64)}
    near, far = ev("safe", -0.2), ev("safe", -0.9)
    out = lv._search_one(_S([noop, far, near]), lv.LiveCfg(prio="as"), snap, 0, {}, lambda: False)
    assert made and made[-1] is near and out.alt
    made.clear()
    out = lv._search_one(_S([noop, far]), lv.LiveCfg(prio="as"), snap, 0, {}, lambda: False)
    assert not made and out["status"] == "noop"
    out = lv._search_one(_S([noop, near]), lv.LiveCfg(prio="as", alt_noop=False), snap, 0, {}, lambda: False)
    assert out["status"] == "noop"


def test_the_planner_follows_a_held_bridge_exactly_when_its_own_checks_pass():
    """fb_hold, the planner side (ForumPlanner.tick with hold_row): the CONTINUE row is the held bridge, enveloped
    first (never cut by the deadline), and chosen whenever it is safe and keeps the commitments - otherwise the
    planner's own choice (its safety keys rank above the hold); without hold_row nothing changes."""
    from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
    from ssbot.combat.planner import PlannerConfig
    from tests.test_forum_planner import FLOOR, FORUM_PARAMS, _ctx, _prefs, _reed_forecaster, _world
    params = km.HeroParams.load(FORUM_PARAMS)
    arena = km.Terrain2D.from_boxes([(10.0, 0.0, 53.0, FLOOR), (10.0, 0.0, 14.01, 30.0), (48.99, 0.0, 53.0, 30.0)])
    n_hold = n_safe = 0
    for x, stab_at, key in ((18.0, None, L), (18.0, 8, R), (22.0, 8, L), (22.0, None, 0), (38.0, 8, R),
                            (38.0, None, L), (26.0, 8, L)):
        f = _reed_forecaster(stab_at).forecast(0.8)
        start = km.initial_state(params, x, FLOOR + params.foot)
        res = []
        for hold in (False, True):
            pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                              ForumConfig(deadline_ms=0.0))
            pl.tick(_world(x), start, km.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, x), _ctx())
            if hold:
                pl.hold_row = np.full(36, key, np.int64)
            r = pl.tick(_world(x), start, km.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, x), _ctx())
            res.append((r, pl))
        (r0, p0), (r1, p1) = res
        ls = p1.last_sel
        N = len(ls["safe"])
        ok_ = bool(ls["safe"][N - 1] and ls["keep"][N - 1] and ls["mkeep"][N - 1])
        assert p1.last_info["env"][N - 1] or ls["S"][N - 1]     # enveloped at deadline 0 unless out at stage 1
        assert (r1.idx == N - 1) == ok_ and (not ok_ or (r1.name == "CONTINUE" and r1.mask == key))
        n_hold += int(r1.idx == N - 1)
        n_safe += int(ok_)
        assert p1.hold_stats["ticks"] == 1
        assert getattr(p0, "hold_stats", None) is None
    assert n_hold == n_safe and 1 <= n_hold < 7
