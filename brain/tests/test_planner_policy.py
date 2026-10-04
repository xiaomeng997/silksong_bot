"""PlannerPolicy glue (ssbot.train.planner_policy, M2 W3 + W4 integration), open loop on the fixture STATEs of the
trial run's wake and first charge (tests/worldstate_fixture.py window 0): every STATE gets a mask, the forecast is
certified from the wake on, the supervisor runs, the hit taken at 56777 is a predicted one, and the stage-C path
(DegradedOracleBackend) runs with its delay."""
import json
import random

import pytest

from ssbot.knowledge.kinematics import Terrain2D
from ssbot.train.encounters import BELL_BEAST
from ssbot.train.planner_policy import PlannerPolicy
from tests import worldstate_fixture as fx

ARENA = [(60.0, 0.0, 110.0, 2.0), (67.2, 0.0, 69.2, 14.0), (102.0, 0.0, 104.0, 14.0)]


class Tap:
    wake_frame = 56532


@pytest.mark.parametrize("view", ["oracle", "degraded"])
def test_policy_runs_open_loop(view):
    pol = PlannerPolicy(view=view, threads=4)
    pol.terrain = Terrain2D.from_boxes(ARENA)
    pol.reset(random.Random(1), BELL_BEAST)
    masks = []
    for s in fx.window(0):
        if s["f"] < 56540:
            continue
        masks.append(pol.act(s, Tap))
    assert len(masks) > 300 and all(isinstance(m, int) and m >= 0 for m in masks)
    st = pol.stats()
    assert st["tick_ms_p50"] is not None and st["view"] == view
    assert 56777 in st["hits_taken"] or view != "oracle"
    assert not st["unpredicted"]
    assert pol.fc.tracker.t_wake is not None
    if view == "degraded":
        assert 2 <= st["k"] <= 4


def _charge_forecast(pol, state: str = "Charge Antic", tau: float = 0.0):
    """A charge from the left anchor, `tau` s into `state` (the walk's tubes; PlannerPolicy's forecaster)."""
    from ssbot.combat.forecast import Ctx, Root
    an = pol.model.anchor("BB_CHARGE", "Set L")
    pol.fc.tracker.roots = lambda origin: ([Root(state, -tau, -tau, Ctx("BB_CHARGE", "Set L", an, "P1", False),
                                                 current=True)], True)
    return pol.fc.forecast(2.0, 0.0), an


def test_forced_clear_counts_frames_until_a_standing_plan_meets_the_support():
    """PlannerPolicy._forced_clear_f, the Q6 clearance (supervisor.SupervisorInput.forced_clear_s) without a planner
    export: a plan standing in a charge's path is clear until the support reaches it (Forecast.t_min, to a frame),
    i-frames that certainly cover the contact remove it, the bound stops at the plan's first attack press, a planner
    export (PlanResult.t_clear) wins, and no plan is unknown."""
    from types import SimpleNamespace

    import numpy as np

    from ssbot.knowledge import kinematics as kin
    pol = PlannerPolicy(view="oracle", threads=2)
    pol.terrain = Terrain2D.from_boxes(ARENA)
    pol.reset(random.Random(1), BELL_BEAST)
    f, an = _charge_forecast(pol)
    p, P, T = pol.params, 1, 120
    y = 2.015 + p.foot
    for dx in (4.0, 12.0, 20.0):
        x = an.x + dx
        S0 = kin.initial_state(p, x, y)
        roll = kin.rollout(S0, np.zeros((1, P + T), np.int64), p, pol.terrain, variants="bounds", threads=2)
        res = SimpleNamespace(hull=roll.bound[0], cmd=np.zeros(T, np.int64), forced_risk=True)
        k = pol._forced_clear_f(res, f, S0, P)
        t = f.t_min(x, 0.5 * (roll.bound[0, 0, 1] + roll.bound[0, 0, 3]), t_max=2.0)
        assert abs((k + P) * p.frame_time - min(t, (P + T) * p.frame_time)) <= 2.5 * p.frame_time, (dx, k, t)
        if k + P < P + T:
            # i-frames past the contact: no contact counts; ending before it: the same contact
            S1 = S0.copy()
            S1.reshape(kin.K, -1)[kin.INV_T, 0] = (P + T + 5) * p.frame_time_max
            assert pol._forced_clear_f(res, f, S1, P) == T
            S1.reshape(kin.K, -1)[kin.INV_T, 0] = max(0.0, (k + P - 3) * p.frame_time)
            assert pol._forced_clear_f(res, f, S1, P) == k
            # an attack pressed before the contact: the bound stops there (hit effects re-roll the plan from it)
            cmd = np.zeros(T, np.int64)
            cmd[max(0, k - 4)] = kin.B_ATTACK
            assert pol._forced_clear_f(SimpleNamespace(hull=roll.bound[0], cmd=cmd, forced_risk=True), f, S0,
                                       P) == max(0, k - 4)
    assert pol._forced_clear_f(SimpleNamespace(hull=None, cmd=np.zeros(0, np.int64), forced_risk=True), f, S0,
                               P) is None
    assert pol._forced_clear_f(SimpleNamespace(hull=None, cmd=np.zeros(0), forced_risk=True, t_clear=77), f, S0,
                               P) == 77


def test_q6_waits_for_forced_risk_within_the_design_horizon():
    """The rule before 2026-10-03 (q6_max_h 2): at h = 2 a FORCED_RISK whose best plan stays clear beyond H = 0.8 s
    (the Charge Emerge triggers of the gate / live QUITs: 120 of 120 frames clear) leaves the attempt going; within H
    it is Q6 and the pause loop presses at once (the pause key in the very mask the policy returns that tick). The
    person's rule (the default, q6_max_h 1): no Q6 at h = 2 within H either, the planner's mask goes out."""
    from ssbot.ipc.framing import BIT
    from ssbot.safety.supervisor import SupervisorConfig
    from ssbot.train.supervision import SupervisedControl
    s = next(x for x in fx.window(0) if x.get("hero") and x["f"] >= 56540)
    s = dict(s, hero=dict(s["hero"], health=3), game=dict(s["game"], paused=False))
    from ssbot.safety.hits_to_death import SupportEvent, SupportSet
    s2 = dict(s, f=s["f"] + 1, q=(s.get("q") or 0) + 166667)
    sc = SupervisedControl(cfg=SupervisorConfig(worst_known_damage=2, q6_max_h=2), support=lambda st: None)
    sc.support = lambda st: SupportSet((SupportEvent("Bone Beast", 2, instance=1),), True)
    r = sc.step(s, plan_s=1, forced_risk=True, forced_clear_s=105 / 60)
    assert r.mask is None and not r.decision.pause_pending and r.decision.h == 2
    r = sc.step(s2, plan_s=1, forced_risk=True, forced_clear_s=27 / 60)
    assert r.decision.pause_pending and "Q6" in r.decision.triggers
    assert r.mask is not None and r.mask & (1 << BIT["pause"]) and r.mask == 1 << BIT["pause"]
    sc = SupervisedControl(cfg=SupervisorConfig(worst_known_damage=2), support=lambda st: None)
    sc.support = lambda st: SupportSet((SupportEvent("Bone Beast", 2, instance=1),), True)
    sc.step(s, plan_s=1, forced_risk=True, forced_clear_s=105 / 60)
    r = sc.step(s2, plan_s=1, forced_risk=True, forced_clear_s=27 / 60)
    assert r.mask is None and not r.decision.pause_pending and r.decision.h == 2 and not r.decision.triggers


def test_yellow_heals_first_and_the_pause_stays_the_fallback():
    """(c) DESIGN §3.7.3 YELLOW at h = 2 (3 of 5 masks after one Bell Beast hit): with silk 9 and the §3.5.6 commit test
    passing at the hero's spot (Forecast.t_min >= 1.52 s) the tactics want the Bind, the planner's own 100-frame Bind
    rollout passes, the Bind is chosen and is no FORCED_RISK, so Q6 cannot pre-empt it; with silk 8 and the hero inside
    an unavoidable eruption the same tick is FORCED_RISK within H: by the person's rule of 2026-10-03 the attempt goes
    on (h 2, no Q6, the least risky plan, the hit weight raised for silk); under the rule before (q6_max_h 2) Q6
    raises PAUSE_PENDING, which forbids the Bind (EVASIVE only: a Bind can be broken into a 0.55 s freeze that
    swallows the pause)."""
    import numpy as np

    from ssbot.combat.boss_model import Anchor
    from ssbot.combat.forecast import Ctx, Root
    from ssbot.combat.safety_filter import FilterContext
    from ssbot.combat.tactics import HEAL
    from ssbot.core.primitives import Prim
    from ssbot.core.worldstate import E, WorldState
    from ssbot.knowledge import kinematics as kin
    from ssbot.knowledge.kinematics import HoldState
    from ssbot.safety.hits_to_death import MASK_NONE, SupportEvent
    from ssbot.safety.supervisor import Supervisor, SupervisorConfig, SupervisorInput

    pol = PlannerPolicy(view="oracle", threads=2)
    pol.terrain = Terrain2D.from_boxes(ARENA)
    pol.reset(random.Random(1), BELL_BEAST)
    p = pol.params

    def ws_at(x, hp, silk):
        ws = WorldState()
        ws.hero.pos = E((x, 3.0544))
        ws.res.hp, ws.res.hp_max, ws.res.silk = E(hp), E(5), E(silk)
        return ws

    def step(sup, hp, res, clear_s=None):
        return sup.step(SupervisorInput(t=1.0, hp=hp, max_hp=5, mask=MASK_NONE, support_known=True,
                                        support=(SupportEvent("Bone Beast", 2, instance=1),), plan_s=res.S,
                                        forced_risk=res.forced_risk, forced_clear_s=clear_s))

    def tick(roots, x, hp, silk, d):
        pol.fc.tracker.roots = lambda origin: (roots, True)
        f = pol.fc.forecast(2.0, 0.0)
        ws = ws_at(x, hp, silk)
        prefs = pol.tac.decide(ws, f, d, d.h)
        ctx = FilterContext.from_world(ws, d, d.h, want_bind=prefs.want_bind)
        S0 = kin.initial_state(p, x, 2.015 + p.foot)
        pol.planner.reset()
        res = pol.planner.tick(ws, S0, HoldState.idle(1), np.zeros(1, np.int64), f, prefs, ctx)
        return res, prefs, f, S0

    sup = Supervisor(SupervisorConfig(worst_known_damage=2))
    d = step(sup, 3, SimpleRes(0, False))
    assert d.tier == "YELLOW" and d.h == 2 and d.allows(Prim.BIND) and not d.pause_pending
    # the boss underground far from the hero: a verified Bind
    res, prefs, f, _ = tick([], 85.0, 3, 9, d)
    assert prefs.mode == HEAL and prefs.want_bind and prefs.t_min >= 1.52
    assert res.name == "BIND" and res.mask & kin.B_BIND and not res.forced_risk
    d2 = step(sup, 3, res)
    assert not d2.pause_pending and "Q6" not in d2.triggers
    # silk 8, inside the burst's eruption as it starts: no Bind, FORCED_RISK within H
    burst = [Root("Burst Out", 0.0, 0.0, Ctx("BB_BURST", None, Anchor(85.0, 5.49, 1), "P1", False), current=True)]
    sup = Supervisor(SupervisorConfig(worst_known_damage=2))
    d = step(sup, 3, SimpleRes(0, False))
    res, prefs, f, S0 = tick(burst, 85.0, 3, 8, d)
    assert res.forced_risk and res.name != "BIND" and not prefs.want_bind
    clear = pol._forced_clear_f(res, f, S0, 1)
    assert clear is not None and clear * p.frame_time <= 0.8
    d2 = step(sup, 3, res, clear * p.frame_time)
    assert not d2.pause_pending and "Q6" not in d2.triggers and d2.h == 2 and d2.allows(Prim.BIND)
    sup = Supervisor(SupervisorConfig(worst_known_damage=2, q6_max_h=2))      # the rule before: Q6 -> PAUSE_PENDING
    d = step(sup, 3, SimpleRes(0, False))
    d2 = step(sup, 3, res, clear * p.frame_time)
    assert d2.pause_pending and "Q6" in d2.triggers and not d2.allows(Prim.BIND)
    # pending: the tactics no longer want the Bind even with silk 9 and room for it, and the filter vetoes it
    res, prefs, _, _ = tick([], 85.0, 3, 9, d2)
    assert prefs.mode != HEAL and not prefs.want_bind and res.name != "BIND" and not res.mask & kin.B_BIND


class SimpleRes:
    def __init__(self, S, forced_risk):
        self.S, self.forced_risk = S, forced_risk


@pytest.mark.parametrize("view", ["oracle", "degraded"])
def test_the_tactics_read_this_ticks_h_not_the_decision_before(view):
    """Fixer review 2026-10-03: the tactics and the safety filter run before the supervisor's step of the tick, and
    used to read the decision of the tick before. On the tick the hero drops from 3 HP (h 2, heal first) to 1 HP with
    the Bind's silk, that decision still said h 2; now they get SupervisedControl.h_now (h 1), so no Bind is wanted on
    that tick either, and Q1 starts the pause loop on it."""
    pol = PlannerPolicy(view=view, threads=2)
    pol.terrain = Terrain2D.from_boxes(ARENA)
    pol.reset(random.Random(1), BELL_BEAST)
    seen = []
    orig = pol.tac.decide

    def spy(ws, f, d, h):
        p = orig(ws, f, d, h)
        seen.append((ws.res.hp.v, None if d is None else d.h, h, p.want_bind))
        return p
    pol.tac.decide = spy
    states = [s for s in fx.window(0) if s.get("hero") and s["f"] >= 56540][:40]
    drop = states[30]["f"]
    for s in states:
        hp = 3 if s["f"] < drop else 1
        s = dict(s, hero=dict(s["hero"], health=hp, silk=9))
        pol.act(s, Tap)
        if pol.sc.pq is not None:
            break
    first_low = next(x for x in seen if x[0] == 1)
    assert first_low[1] == 2 and first_low[2] == 1 and not first_low[3]   # the decision before said 2; h_now 1
    assert all(not x[3] for x in seen if x[2] is not None and x[2] <= 1)
    assert pol.decision.pause_pending and "Q1" in pol.decision.triggers


def test_once_the_pause_machine_owns_the_keys_no_planner_key_reaches_the_game(tmp_path, monkeypatch):
    """(a) and the pause-safety audit: the fixture's fight (randomize_start left 2 HP: Q1 once the boss is in support)
    against a stand-in game that pauses on a Pause edge with the gate open, ACTIONs applied 2 frames after their
    STATE. From the trigger
    tick on the policy returns only the pause machine's keys (Pause in the loop, nothing from the first pause cue on:
    an emulated quit presses no menu key), the planner is not ticked again (its mask would be discarded), and the
    decision log's rows of the trigger tick are written only once the loop has stopped."""
    import copy

    from ssbot.ipc.framing import BIT
    from ssbot.safety import game_codes as gc
    P = 1 << BIT["pause"]
    pol = PlannerPolicy(view="oracle", threads=2, log_dir=tmp_path, instance=0)
    pol.terrain = Terrain2D.from_boxes(ARENA)
    pol.reset(random.Random(1), BELL_BEAST)
    ticks = []
    real_tick = pol.planner.tick
    monkeypatch.setattr(pol.planner, "tick", lambda *a, **k: ticks.append(1) or real_tick(*a, **k))
    log = tmp_path / "decisions_i0.jsonl"
    sent: dict[int, int] = {}
    out, paused_f, trig, n_at_trigger, logged_at_trigger = [], None, None, None, None
    for s in fx.window(0):
        f = s["f"]
        if f < 56540:
            continue
        s = copy.deepcopy(s)
        if paused_f is None and trig is not None and sent.get(f, 0) & P and not sent.get(f - 1, 0) & P \
                and not s["pause"]["blk"]:
            paused_f = f
        if paused_f is not None:
            age = f - paused_f
            s["ev"], s["ts"] = [], 0.0
            s["game"].update(gs=gc.GS_PAUSED, ui=gc.UI_PAUSED, menu=gc.MENU_PAUSE_MENU if age >= 8 else 6,
                             fading=age < 8, paused=True)
            s["pause"]["blk"] = 100 if age < 8 else 68 if age < 19 else 64
        m = pol.act(s, Tap)
        sent[f + 2] = m
        out.append((f, m, pol.sc.pq.state if pol.sc.pq is not None else None))
        if trig is None and pol.first_pending_f is not None:
            trig, n_at_trigger = f, len(ticks)
            logged_at_trigger = log.exists() and any(json.loads(x)["f"] == f
                                                     for x in log.read_text("utf-8").splitlines())
        if pol.episode_outcome is not None:
            break
    assert trig is not None and paused_f is not None and paused_f <= trig + 2 + 6
    assert pol.episode_outcome == "QUIT" and pol.sc.pq.outcome == "QUIT_EMULATED"
    after = [(f, m, st) for f, m, st in out if f >= trig]
    assert all(m & ~P == 0 for _, m, _ in after)                     # never a planner key once the machine owns them
    assert after[0][1] == P                                          # the trigger tick's own mask is the press
    assert all(m == 0 for f, m, _ in after if f >= paused_f)         # nothing from the cue on (emulated quit)
    assert len(ticks) == n_at_trigger                                # the planner is not ticked again
    assert logged_at_trigger is False                                # not on the trigger tick, before its keys
    rows = [json.loads(x) for x in log.read_text("utf-8").splitlines()]
    assert any(r["f"] == trig and r["pending"] for r in rows)        # written once the loop stopped
    assert any(r.get("plan") == "PAUSE" for r in rows)
    # the key plan log: one record for the episode, the pause machine's press a supervisor note
    st = pol.stats()
    krec = [json.loads(x) for x in (tmp_path / "keys_i0.jsonl").read_text("utf-8").splitlines()]
    assert len(krec) == 1 and krec[0]["ticks"] == len(out) and krec[0]["sup_ticks"] > 0
    assert any(n[0] == "pause" and n[6] for n in krec[0]["notes"])
    assert st["keys"] is not None and st["keys"]["supervisor_notes"] >= 1
    assert pol.stats()["keys"] is None                                # written once per episode


def test_bind_reserve_reaches_the_safety_filter():
    """The playbook's bind.reserve_at_full_hp (off for Bell Beast) goes into the filter context: with it on, no
    Silkspear candidate is allowed at full HP with 9 silk; off, they are."""
    import numpy as np

    from ssbot.combat import candidates as cmod
    from ssbot.combat.safety_filter import R_SILK, FilterContext, veto
    from ssbot.combat.tactics import load_playbook
    from ssbot.core.primitives import N_PRIM, Prim
    assert load_playbook("BellBeast").bind_reserve_at_full_hp is False
    cs = cmod.build(48)
    spear = (cs.prim_bits & (1 << int(Prim.SILKSKILL))) != 0
    assert spear.any()
    for reserve, allowed in ((False, True), (True, False)):
        ctx = FilterContext(allowed_mask=np.ones(N_PRIM, bool), hp=5, max_hp=5, silk=9, h=3, tier="GREEN",
                            silk_reserve_full_hp=reserve)
        ok, why = veto(cs, ctx)
        assert ok[spear].any() == allowed and (why[spear] == R_SILK).all() == (not allowed)


def test_skipped_states_reach_the_perception_path():
    """A late tick skips STATEs (the episode loop hands the policy only the newest): the skipped ones still go
    through the backend (filter, noise, delay line) in order, so their events (a hit dealt) are not lost."""
    class Link:
        def __init__(self):
            self.subs = []

        def subscribe_raw(self, fn):
            pass

        def subscribe_state(self, fn):
            self.subs.append(fn)

    pol = PlannerPolicy(view="degraded", threads=4)
    link = Link()
    pol.attach(link)
    pol.terrain_tap = None                       # no TERRAIN messages here
    pol.terrain = Terrain2D.from_boxes(ARENA)
    pol.reset(random.Random(1), BELL_BEAST)
    fed = []
    orig = pol.backend.feed
    pol.backend.feed = lambda s: (fed.append(s["f"]), orig(s))[1]
    frames = [s for s in fx.window(0) if s["f"] >= 56540][:121]
    acted = []
    for i, s in enumerate(frames):
        for fn in link.subs:
            fn(s)
        if i % 3 == 0:
            pol.act(s, Tap)
            acted.append(s["f"])
    assert fed == [s["f"] for s in frames if s["f"] <= acted[-1]]
    assert pol.counts["caught_up"] > 0
