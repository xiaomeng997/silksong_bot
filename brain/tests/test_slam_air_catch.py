"""11-14 the re-pogo entry (连踩入口; docs/plans/forum_clapper_committed_chain.md 4.4a; the person 11-14 quotes 140, 141 "还是先把
连踩入口给写了"; SSBOT_FORUM_AIRSTRIKE, default off): SP13a's air catch is also tried in the air past the start frames, behind S,
too close to it and with no landing in time (the run waits in the air), and from a chain's air context with no link running
(SlamPlay.air_catch_try, asked by the policy). Off: unchanged."""
from collections import Counter
from types import SimpleNamespace as NS

import pytest

from ssbot.combat import air_chain as ac
from ssbot.combat import claw_strike as cs
from ssbot.combat import slam_play as sp
from ssbot.train import forum_planner_policy as mod
from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
from tests.test_b2_policy_priority import Script, run_arbitration, selected
from tests.test_slam_play import state
from tests.test_sp13 import sim_for

CX = 31.0                               # S's centre; state()'s Clapper faces left (flipX False): in front = left


def air(f, k, hx, up=6.0, vy=2.0, st="Slam Antic", silk=3):
    """STATE of frame f with S at antic frame k - SEND_AHEAD (the run's k is the mask's frame) and her up in the air."""
    s = state(f, st, (k - sp.SEND_AHEAD) / 60.0, hx=hx, ground=False, vy=vy)
    s["hero"]["silk"] = silk
    s["hero"]["box"] = [hx - 0.23, cs.FLOOR + up, hx + 0.23, cs.FLOOR + up + 2.07]
    s["hero"]["pos"] = [hx, cs.FLOOR + up + cs.POS_DY]
    return s


def t_of(f):
    return 10.0 + (f - 1000) / 60.0


@pytest.fixture
def spy(monkeypatch):
    """SlamPlay._as_try stand-in: records (k, why), no plan (a failed search's RESEARCH_F wait, as the real one)."""
    calls = []

    def fake(self, r, k, f, s, e, ground, accepting, sim, hp, t, why):
        calls.append((k, why))
        r.cs_next = f + 2 + ac.RESEARCH_F
        return None
    monkeypatch.setattr(sp.SlamPlay, "_as_try", fake)
    return calls


def test_defaults_off():
    assert not cs.AIRSTRIKE and sp.AS_K_MAX == 40
    p = sp.SlamPlay(sp.PlayCfg())
    hx = CX - 6.5
    assert p.air_catch_try(1000, air(1000, 12, hx), False, True, t_game=10.0, sim=sim_for(hx, ground=False, bb=6.0)) is None
    assert p.run is None and p.as_tries == [0, 0]


@pytest.mark.parametrize("on,ground,k,kept", [(True, False, 32, True), (True, False, 40, True), (True, False, 41, False),
                                              (True, True, 32, False), (False, False, 32, False)])
def test_late_in_the_air_keeps_the_run_for_the_air_catch(monkeypatch, spy, on, ground, k, kept):
    # _try_start's late (past the ground start's frames): in the air up to AS_K_MAX the run stays and step routes it to
    # _cs_try (the Clawline off: straight to the air catch); else it ends 'late' as before
    monkeypatch.setattr(cs, "AIRSTRIKE", on)
    monkeypatch.setattr(cs, "CLAWSTRIKE", False)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    s = air(1000, k, hx)
    p.step(1000, s, ground, t_game=10.0, sim=sim_for(hx, ground=ground, bb=0.0 if ground else 6.0))
    if kept:
        assert p.run is not None and p.run.phase == "wait" and p.run.why == "late" and not p.done
        assert spy == [(k, "late")]
    else:
        assert p.run is None and p.done[-1].why == "late" and spy == []


@pytest.mark.parametrize("hx_off,k,ground,called", [(-3.0, 10, False, "behind"), (-3.0, 10, True, None),
                                                    (6.0, 20, False, "force"), (6.0, 20, True, None)])
def test_clawline_behind_and_late_fall_back_to_the_air_catch(monkeypatch, spy, hx_off, k, ground, called):
    # the Clawline on: behind S, or in front past its last frame (14): its decline goes on to the air catch in the air only
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    monkeypatch.setattr(cs, "CLAWSTRIKE", True)
    hx = CX - hx_off                                       # hx_off > 0: in front (left of S), < 0: behind it
    p = sp.SlamPlay(sp.PlayCfg())
    p.step(1000, air(1000, k, hx), ground, t_game=10.0, sim=sim_for(hx, ground=ground, bb=0.0 if ground else 6.0))
    if called is None:
        assert spy == []
    else:
        assert spy and spy[0] == (k, called)
        assert ("behind" if called == "behind" else "late") in p.cs_declines


def test_the_old_fallback_reasons_only_when_off(monkeypatch, spy):
    # AIRSTRIKE off and the Clawline on: a late Clawline ends the run (no air catch), as before
    monkeypatch.setattr(cs, "AIRSTRIKE", False)
    monkeypatch.setattr(cs, "CLAWSTRIKE", True)
    hx = CX - 6.0
    p = sp.SlamPlay(sp.PlayCfg())
    p.step(1000, air(1000, 20, hx), False, t_game=10.0, sim=sim_for(hx, ground=False, bb=6.0))
    assert spy == [] and p.run is None and p.done[-1].why == "late"


@pytest.mark.parametrize("on", [False, True])
def test_no_landing_in_time_waits_in_the_air(monkeypatch, spy, on):
    # SP13a's case (6 u up, rising slowly, 6.5 u in front): the air entry at k 10 ('land'), then no landing by K_JUMP_LATE2;
    # off: the run ends 'no landing (fall)'; on: the air catch is tried and, with no plan, the run waits in the air
    monkeypatch.setattr(cs, "AIRSTRIKE", on)
    monkeypatch.setattr(cs, "CLAWSTRIKE", False)
    monkeypatch.setattr(sp, "LATE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    p.step(1000, air(1000, 10, hx), False, t_game=10.0, sim=sim_for(hx, ground=False, bb=6.0, vy=2.0))
    assert p.run.phase == "land"
    m = p.step(1001, air(1001, 11, hx), False, t_game=t_of(1001), sim=sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0))
    assert m is None
    if not on:
        assert p.run is None and p.done[0].why.startswith("no landing") and spy == []
        return
    assert p.run is not None and p.run.phase == "wait" and p.run.why == "no landing" and not p.done
    assert spy == [(11, "no landing")]
    # the next ticks: the wait phase routes it to the air catch again after RESEARCH_F
    for f in range(1002, 1002 + ac.RESEARCH_F + 1):
        p.step(f, air(f, 11 + f - 1001, hx), False, t_game=t_of(f), sim=sim_for(hx, f=f, ground=False, bb=6.0, vy=2.0))
    assert len(spy) == 2 and p.run is not None and p.run.phase == "wait"


def test_no_landing_past_as_k_max_ends_as_before(monkeypatch, spy):
    # the land phase's wait only up to AS_K_MAX: a run first stepped again at antic 42 with no landing ends as before
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    monkeypatch.setattr(cs, "CLAWSTRIKE", False)
    monkeypatch.setattr(sp, "LATE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    p.step(1000, air(1000, 10, hx), False, t_game=10.0, sim=sim_for(hx, ground=False, bb=6.0, vy=2.0))
    assert p.run.phase == "land"
    p.step(1032, air(1032, 42, hx), False, t_game=t_of(1032), sim=sim_for(hx, f=1032, ground=False, bb=6.0, vy=2.0))
    assert p.run is None and p.done[-1].why.startswith("no landing")


def test_on_the_ground_no_clawline_detour(monkeypatch):
    # on the ground the air catch's new reasons (behind, too close) do not route the run to _cs_try at all
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    monkeypatch.setattr(cs, "CLAWSTRIKE", True)
    calls = []
    monkeypatch.setattr(sp.SlamPlay, "_cs_try", lambda self, r, k, f, s, e, g, a, sim, hp, t, why: calls.append(why))
    for hx in (CX + 3.0, CX - 1.0):                            # behind S; in front but inside the reach band (too close)
        p = sp.SlamPlay(sp.PlayCfg())
        s = air(1000, 10, hx)
        p.step(1000, s, True, t_game=10.0, sim=sim_for(hx))
        assert p.run is not None and p.run.why in ("behind", "distance %.1f" % (CX - hx))
    assert calls == []


@pytest.mark.parametrize("case", ["ground", "input", "run", "idle", "late", "nosim", "handled", "hold"])
def test_air_catch_try_gates(monkeypatch, spy, case):
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    s, k, ground, accepting, sim = air(1000, 20, hx), 20, False, True, sim_for(hx, ground=False, bb=6.0)
    if case == "ground":
        ground = True
    elif case == "input":
        accepting = False
    elif case == "run":
        p.run = sp.Run(iid=8, fa=990, face=-1)
    elif case == "idle":
        s = air(1000, 20, hx, st="Idle")
    elif case == "late":
        s = air(1000, sp.AS_K_MAX + 1, hx)
    elif case == "nosim":
        sim = None
    elif case == "handled":
        p._closed_iid = 7
        p._closed_ta[7] = 10.0 - (k - sp.SEND_AHEAD) / 60.0
    elif case == "hold":
        p._hold = (8, 9.9, 9)
    assert p.air_catch_try(1000, s, ground, accepting, t_game=10.0, sim=sim) is None
    assert spy == [] and p.as_tries == [0, 0]
    assert p.run is None or case == "run"


def test_air_catch_try_keeps_no_run_without_a_plan_and_waits(monkeypatch, spy):
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    for f in range(1000, 1000 + ac.RESEARCH_F + 2):
        k = 20 + f - 1000
        assert p.air_catch_try(f, air(f, k, hx), False, True, t_game=t_of(f),
                               sim=sim_for(hx, f=f, ground=False, bb=6.0)) is None
        assert p.run is None
    # searched at 1000, again RESEARCH_F frames later (the mask frame f + 2 >= the wait's end)
    assert spy == [(20, "air context"), (20 + ac.RESEARCH_F, "air context")]
    assert p.as_tries == [2, 0] and p._as_next[7] == 1000 + ac.RESEARCH_F + 2 + ac.RESEARCH_F


def test_air_catch_try_takes_a_real_plan_as_a_committed_link(monkeypatch):
    # SP13a's case through the chain-context entry: the real air_chain search (S as B); the plan is a committed link
    # (cs_strike), and the playbook's ordinary step carries it on the next tick
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    m = p.air_catch_try(1001, air(1001, 11, hx), False, True, t_game=t_of(1001),
                        sim=sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0))
    r = p.run
    assert m is not None and r is not None and r.as_air and r.phase == "cs_strike" and r.cs_strike is not None
    assert 46 <= r.cs_strike.k_press <= 48 and r.cs_log[-1][1] == "as_plan" and r.cs_log[-1][2] == "air context"
    assert p.committed(air(1001, 11, hx)) and p.as_tries == [1, 1]
    m2 = p.step(1002, air(1002, 12, hx), False, t_game=t_of(1002), sim=sim_for(hx, f=1002, ground=False, bb=6.0, vy=2.0))
    assert p.run is r and r.as_air and m2 is not None
    st = p.stats()
    assert st["as_runs"] == 1 and st["as_ctx_tries"] == 1 and st["as_ctx_plans"] == 1
    assert r.cs_strike.k_press == 47                       # the air catch searches the K_PRESS 47 stage only (cost)


def test_search_stages_default_and_the_47_stage():
    # air_chain.search's default tries 47 then 46 / 48; the air catch passes the 47 stage alone (same plan in SP13a's case)
    hx = CX - 6.5
    ctx = ac.Ctx(b_iid=7, b_x=CX, b_y=cs.FLOOR + 4.434, b_face=-1, kb0=1001 - (1001 - 9), a_box=None, hero_x=hx, face=1,
                 tls=ac.timelines())
    full = ac.search(sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0), ctx)
    one = ac.search(sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0), ctx, stages=sp.AS_STAGES)
    assert sp.AS_STAGES == ((47,),) and full is not None and one is not None
    assert (one.k_press, one.f_press, one.d_end, one.f_umb, one.f_down) == (full.k_press, full.f_press, full.d_end,
                                                                            full.f_umb, full.f_down)
    assert ac.search(sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0), ctx, stages=()) is None


def test_failed_searches_per_slam_are_capped(monkeypatch):
    # AS_FAIL_MAX failed searches give up that slam (step and air_catch_try share the count); a new slam is searched again
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    calls = []

    def fake(sim, ctx, stages=None):
        calls.append(stages)
        return None
    monkeypatch.setattr(ac, "search", fake)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    f = 1000
    for i in range(sp.AS_FAIL_MAX + 3):
        f = 1000 + i * (ac.RESEARCH_F + 1)
        p.air_catch_try(f, air(f, 12 + f - 1000, hx), False, True, t_game=10.0, sim=sim_for(hx, f=f, ground=False, bb=6.0))
    assert len(calls) == sp.AS_FAIL_MAX and all(st == sp.AS_STAGES for st in calls)
    # the same Clapper's next slam (its antic entry 60 frames later): searched again
    f2 = f + 60
    p.air_catch_try(f2, air(f2, 12, hx), False, True, t_game=10.0 + 60 / 60.0, sim=sim_for(hx, f=f2, ground=False, bb=6.0))
    assert len(calls) == sp.AS_FAIL_MAX + 1


class AirSlam(Script):
    """The playbook stand-in with the chain-context entry."""
    def __init__(self, mask=16, ac_mask=48):
        super().__init__(mask=mask)
        self.ac_mask, self.air_calls, self.yield_calls = ac_mask, [], []
        self.run = None

    def air_catch_try(self, f, s, ground, accepting=True, **kw):
        self.air_calls.append((f, ground, accepting, sorted(kw)))
        if self.ac_mask is not None:
            self.run = NS(phase="cs_strike", k=30)
        return self.ac_mask

    def yield_ends_run(self, s):
        self.yield_calls.append(s["f"])
        return False


def arb(monkeypatch, on=True, offer=False, runner=None, ac_mask=48, veto=False, **kw):
    # offer: the chain's B2 offer is this tick's planner result (it takes the keys); else the planner's own row while the
    # chain only generates candidates (its air context)
    monkeypatch.setattr(mod.claw_strike, "AIRSTRIKE", on)
    monkeypatch.setattr(mod.slam_play, "COMMIT", True)        # package 1 follows v2 (on in production): its yield check runs
    monkeypatch.setattr(mod.air_chain, "ChainSim", lambda *a: "SIM")
    p, res = selected("approach", 2)
    if not offer:
        p.chain_native._b2_selected = None
        p.planner = NS(last_info={})
        res = NS(name="WAIT+idle", mask=0)
    if runner is not None:
        p.chain_native.runner = runner
    p.params = p.terrain = None
    if veto:
        p._rune_veto = lambda who, m: who == "slam"
    slam = AirSlam(ac_mask=ac_mask)
    out = run_arbitration(p, res, slam=slam, **kw)
    return p, slam, out


def test_policy_asks_the_air_catch_in_an_idle_chain_air_context(monkeypatch):
    # the chain has an air context (candidate_generation) and no link running: the playbook is not stepped, only its
    # air catch asked; a plan takes the keys from the planner (the run counts as stepped: no yield end this tick)
    p, slam, out = arb(monkeypatch)
    assert not slam.stepped and len(slam.air_calls) == 1 and slam.yield_calls == []
    f, ground, accepting, kws = slam.air_calls[0]
    assert (f, ground, accepting) == (2599, True, True) and kws == ["guard", "sim", "skip", "t_game"]
    assert (out["own"], out["mask"], out["play"]) == ("slam", 48, 48)
    assert p.counts["slam_air_catch"] == 1 and p._play_tick["why"] == "air catch"


def test_policy_rune_exit_veto_drops_the_air_catch(monkeypatch):
    # the rune exit veto as for the playbook's own keys: the run aborted, the keys stay as before
    p, slam, out = arb(monkeypatch, veto=True)
    assert len(slam.air_calls) == 1 and slam.aborted == ["rune exit"] and out["own"] != "slam"
    assert p.counts["slam_air_catch"] == 0


def test_policy_no_plan_leaves_the_rest_as_before(monkeypatch):
    # no plan: the lower scripts' order runs on as with the switch off (here the Clawline chase stand-in takes the keys)
    p, slam, out = arb(monkeypatch, ac_mask=None)
    p0, slam0, out0 = arb(monkeypatch, on=False)
    assert len(slam.air_calls) == 1 and slam0.air_calls == [] and p.counts["slam_air_catch"] == 0
    assert (out["own"], out["mask"], out["play"]) == (out0["own"], out0["mask"], out0["play"]) and out["own"] != "slam"


@pytest.mark.parametrize("why,kw", [("off", {"on": False}), ("chain offer", {"offer": True}),
                                    ("link running", {"runner": NS(run=object())}),
                                    ("low_crit", {"low_crit": True}), ("asw_crit", {"asw_crit": True}),
                                    ("supervisor", {"mask_sup": 512}), ("m2", {"m2": NS(took=False)})])
def test_policy_does_not_ask_the_air_catch(monkeypatch, why, kw):
    p, slam, out = arb(monkeypatch, **kw)
    assert slam.air_calls == [] and p.counts["slam_air_catch"] == 0, why
    assert out["own"] != "slam"


class BounceChain:
    """A B2 chain stand-in whose own real bounce is this STATE's (Task 181's hand-off from any script phase)."""
    arm = "B"
    _transfer_goal = None

    def __init__(self):
        self.calls = []

    def observe_bounce_goal(self, state, prefs, run, game_time=None):
        return True

    def own_bounce_now(self, state):
        return True

    def goal_preferences(self, state, prefs, *, handoff):
        self.calls.append(handoff)
        return NS(**vars(prefs))


def bounce_policy(run):
    p = Policy.__new__(Policy)
    p.chain_native = BounceChain()
    aborted = []
    p.slam_play = NS(run=run, committed=lambda s: run.phase in sp.COMMIT_PHASES, abort=aborted.append)
    p.tac = None
    return p, aborted


def test_the_chains_own_bounce_does_not_take_back_an_air_catch(monkeypatch):
    # runtime354 ep17 57075-57076: the air catch made on the hand-back tick was aborted on the next by the chain's own bounce
    monkeypatch.setattr(mod.slam_play, "COMMIT", True)
    prefs = NS(target=8)
    p, aborted = bounce_policy(NS(phase="cs_strike", as_air=True, bounced=False))
    assert p._chain_goal_preferences({"f": 1030}, prefs) is prefs
    assert p.chain_native.calls == [] and not aborted
    # any other script run (the Clawline's strike, a waiting look) is still taken back by the chain's own bounce
    for run in (NS(phase="cs_strike", as_air=False, bounced=False), NS(phase="wait", as_air=False, bounced=False)):
        p, aborted = bounce_policy(run)
        assert p._chain_goal_preferences({"f": 1030}, prefs) is not prefs
        assert p.chain_native.calls == [True] and aborted == ["observed target transfer: goal handoff"]


def test_chain_air_context_idle_reads_the_links():
    p = Policy.__new__(Policy)
    p.chain_native = None
    assert not p._chain_air_context_idle()
    p.chain_native = NS(candidate_generation=False)
    assert not p._chain_air_context_idle()
    p.chain_native = NS(candidate_generation=True, runner=NS(run=None), commitment=None, recovery=None)
    assert p._chain_air_context_idle()
    for k, v in (("runner", NS(run=object())), ("commitment", object()), ("recovery", object())):
        p.chain_native = NS(**{**dict(candidate_generation=True, runner=NS(run=None), commitment=None, recovery=None), k: v})
        assert not p._chain_air_context_idle(), k
