"""11-14 the re-pogo entry (连踩入口; docs/plans/forum_clapper_committed_chain.md 4.4a; the person 11-14 quotes 140, 141 "还是先把
连踩入口给写了"; SSBOT_FORUM_AIRSTRIKE, default off): SP13a's air catch is also tried in the air past the start frames, behind S,
too close to it and with no landing in time (the run waits in the air), and from a chain's air context with no link running
(SlamPlay.air_catch_try, asked by the policy). Off: unchanged."""
from collections import Counter
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import air_chain as ac
from ssbot.combat import claw_strike as cs
from ssbot.combat import slam_play as sp
from ssbot.knowledge import kinematics as kin
from ssbot.train import forum_planner_policy as mod
from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
from tests.test_b2_policy_priority import Script, run_arbitration, selected
from tests.test_slam_play import state
from tests.test_sp13 import PARAMS, TERR, sim_for

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


@pytest.fixture
def no_plan(monkeypatch):
    """air_chain.search stand-in: records (stages, strict), no plan."""
    calls = []

    def fake(sim, ctx, stages=None, strict=False):
        calls.append((stages, strict))
        return None
    monkeypatch.setattr(ac, "search", fake)
    return calls


def test_air_catch_try_keeps_no_run_without_a_plan_and_waits(monkeypatch, no_plan):
    # a failed search: no run kept; the slam's record waits RESEARCH_F game frames, then searches again (the 47 stage,
    # the strict protection)
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    for f in range(1000, 1000 + ac.RESEARCH_F + 2):
        k = 20 + f - 1000
        assert p.air_catch_try(f, air(f, k, hx), False, True, t_game=t_of(f),
                               sim=sim_for(hx, f=f, ground=False, bb=6.0)) is None
        assert p.run is None
    assert no_plan == [(sp.AS_STAGES, True)] * 2
    assert p.as_tries == [2, 0] and p._as_slams[7]["fails"] == 2


def test_a_paused_game_clock_is_one_slam(monkeypatch, no_plan):
    # Sol seq366 D426-SEARCH-BOUND: STATE frames 1000 -> 1009 while the game clock stands at t 10 (tin 0.2, a hit-stop): one
    # slam (its antic entry on the game clock, 9.8), no second search before RESEARCH_F game frames
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    for f in (1000, 1003, 1006, 1009):
        p.air_catch_try(f, air(f, 14, hx), False, True, t_game=10.0, sim=sim_for(hx, f=f, ground=False, bb=6.0))
    assert len(no_plan) == 1 and list(p._as_slams) == [7] and p._as_slams[7]["fails"] == 1
    assert abs(p._as_slams[7]["ta"] - 9.8) < 1e-9


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


def test_failed_searches_per_slam_are_capped(monkeypatch, no_plan):
    # AS_FAIL_MAX failed searches give up that slam (one record per slam instance); the next slam is searched again
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    f = 1000
    for i in range(sp.AS_FAIL_MAX + 3):
        f = 1000 + i * ac.RESEARCH_F
        p.air_catch_try(f, air(f, 6 + i * ac.RESEARCH_F, hx), False, True, t_game=t_of(f),
                        sim=sim_for(hx, f=f, ground=False, bb=6.0))
    assert no_plan == [(sp.AS_STAGES, True)] * sp.AS_FAIL_MAX and p._as_slams[7]["fails"] == sp.AS_FAIL_MAX
    # the same Clapper's next slam (its antic entry 78 game frames later): searched again, its own count
    f2 = f + 60
    p.air_catch_try(f2, air(f2, 12, hx), False, True, t_game=t_of(f2), sim=sim_for(hx, f=f2, ground=False, bb=6.0))
    assert len(no_plan) == sp.AS_FAIL_MAX + 1 and p._as_slams[7]["fails"] == 1


def committed(monkeypatch):
    """SP13a's case taken by air_catch_try with the real search: the committed run's SlamPlay."""
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    assert p.air_catch_try(1001, air(1001, 11, hx), False, True, t_game=t_of(1001),
                           sim=sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0)) is not None
    return p, hx


def test_committed_re_search_shares_the_stage_and_the_budget(monkeypatch):
    # Sol seq366 D426-SEARCH-BOUND: the committed plan no longer passing (its strict verify) searches again with the 47 stage
    # and the strict protection, the failure counted on the slam's record (no down slash sent: nothing to bind)
    p, hx = committed(monkeypatch)
    calls = []
    monkeypatch.setattr(ac, "verify", lambda sim, ctx, plan, strict=False: calls.append(("verify", strict)) and None)
    monkeypatch.setattr(ac, "search", lambda sim, ctx, stages=None, strict=False, sent=None:
                        calls.append(("search", stages, strict, sent)) and None)
    p.step(1002, air(1002, 12, hx), False, t_game=t_of(1002), sim=sim_for(hx, f=1002, ground=False, bb=6.0, vy=2.0))
    assert calls == [("verify", True), ("search", sp.AS_STAGES, True, None)] and p._as_slams[7]["fails"] == 1


def test_committed_re_search_inside_the_used_budget_does_not_search(monkeypatch):
    p, hx = committed(monkeypatch)
    p._as_slams[7]["fails"] = sp.AS_FAIL_MAX
    calls = []
    monkeypatch.setattr(ac, "verify", lambda sim, ctx, plan, strict=False: None)
    monkeypatch.setattr(ac, "search", lambda sim, ctx, stages=None, strict=False, sent=None: calls.append(1))
    p.step(1002, air(1002, 12, hx), False, t_game=t_of(1002), sim=sim_for(hx, f=1002, ground=False, bb=6.0, vy=2.0))
    assert calls == [] and p._as_slams[7]["fails"] == sp.AS_FAIL_MAX
    assert p.run is None and p.done[-1].why == "as no strike"           # its press far: no keep


def other(iid, x, st):
    return {"type_key": sp.CLAPPER, "iid": iid, "hp": 200, "pos": [x, 7.45], "flipX": False,
            "fsms": [{"name": "Control", "state": st, "t": 0.3}]}


@pytest.mark.parametrize("case", ["clean", "other idle", "other jump", "other slam", "big circle", "small rune", "two_play"])
def test_air_catch_known_hazards_at_entry(monkeypatch, case):
    # Sol seq366 D426-HAZARDS: SP13a's feasible catch, plus the other one in its jump (its landing hammer to come) or in a slam,
    # a placed big circle or small rune lit on her modelled path, or TWO_PLAY's other-one gate: declined, the failure
    # counted; clean (or the other one idle far away): the plan takes the keys
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    s = air(1001, 11, hx)
    bombs = None
    if case.startswith("other"):
        s["ents"].append(other(8, 45.0, {"other idle": "Idle", "other jump": "Air", "other slam": "Slam Antic"}[case]))
    elif case == "big circle":
        monkeypatch.setattr(p._life, "rows", lambda t=None: np.array([[9.0, 27.0, 8.0, 7.2, 0.0, 90.0]]))
    elif case == "small rune":
        bombs = np.array([[9.0, hx, cs.FLOOR + 7.0, 1.2, 0.0, 90.0]])
    elif case == "two_play":
        monkeypatch.setattr(sp, "TWO_PLAY", True)
        monkeypatch.setattr(p, "_two_danger", lambda s_, e_, tx, t, k=None: "other test")
    m = p.air_catch_try(1001, s, False, True, t_game=t_of(1001), sim=sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0),
                        bombs=bombs)
    if case in ("clean", "other idle"):
        assert m is not None and p.run is not None and p.run.as_air and p.run.cs_log[-1][1] == "as_plan"
        return
    assert m is None and p.run is None and p.cs_declines.get("as hazard") == 1 and p._as_slams[7]["fails"] == 1


@pytest.mark.parametrize("st", ["Jump Antic", "Spell Antic"])
def test_committed_air_catch_ends_on_a_new_hazard(monkeypatch, st):
    # the committed run re-reads the known hazards every tick: the other one starting a move ends it (the planner decides)
    p, hx = committed(monkeypatch)
    s = air(1002, 12, hx)
    s["ents"].append(other(8, 45.0, st))
    m = p.step(1002, s, False, t_game=t_of(1002), sim=sim_for(hx, f=1002, ground=False, bb=6.0, vy=2.0))
    assert m is None and p.run is None and p.done[-1].why == "as hazard"


class RO:
    def __init__(self, box, flags):
        self.box, self.flags = box, flags


@pytest.mark.parametrize("hazard,strict_bad,old_bad", [("a body", 9, -1), ("b body", -1, -1), ("b hammer", 9, -1)])
def test_pre_contact_protection_only_for_the_contacted_body(monkeypatch, hazard, strict_bad, old_bad):
    # Sol seq366 D426-PROTECTION: B's contact at index 10, none on A, no F_INVULN; her box meets one hazard at index 9 only.
    # The historical rule clears all three; with owners only the contacted B's body (the chosen target rule), never A's
    # body, never B's hammer; real F_INVULN still clears them
    T1 = 14
    box = np.tile(np.array([0.0, 0.0, 1.0, 1.0]), (1, T1, 1))
    box[0, 9] = [10.0, 0.0, 11.0, 1.0]
    far = np.tile(np.array([100.0, 0.0, 101.0, 1.0]), (T1, 1))
    near = far.copy()
    near[9] = [10.5, 0.0, 12.0, 2.0]
    kind = {"b body": "root", "b hammer": "hammer"}.get(hazard)
    monkeypatch.setattr(ac, "_b_boxes", lambda ctx, tl, idx, k: (near if k == kind else far)[np.asarray(idx)])
    ctx = NS(a_box=[10.5, 0.0, 12.0, 2.0] if hazard == "a body" else None)
    flags = np.zeros((1, T1), np.int64)
    args = (ctx, None, np.array([[-1, 10]]), np.array([13]))
    assert ac._first_unsafe(RO(box, flags), *args, owners=np.array([[0, 1]]))[0] == strict_bad
    assert ac._first_unsafe(RO(box, flags), *args)[0] == old_bad
    flags[0, 9] = kin.F_INVULN
    assert ac._first_unsafe(RO(box, flags), *args, owners=np.array([[0, 1]]))[0] == -1


def test_contact_owner_bits():
    # the down slash's contact owner: B (1), A (2), both on the same frame (3), neither alone (0: both shapes split)
    j, jb, ja = np.array([5, 5, 5, 5, -1]), np.array([5, 7, 5, -1, -1]), np.array([-1, 5, 5, 6, -1])
    assert ac._owner_bits(j, jb, ja).tolist() == [1, 2, 3, 0, 0]


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
    assert (f, ground, accepting) == (2599, True, True) and kws == ["bombs", "guard", "sim", "skip", "t_game"]
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


def test_strict_search_passes_the_contact_owners(monkeypatch):
    # evaluate(strict) gives _first_unsafe the contacts' owners (the strike's column: B); the default keeps the historical
    # rule (None) for the Clawline's strike and SP10b
    seen = []
    real = ac._first_unsafe

    def spy_(ro, ctx, tl, contacts, i_end, i_from=None, owners=None):
        seen.append(None if owners is None else np.asarray(owners).copy())
        return real(ro, ctx, tl, contacts, i_end, i_from, owners)
    monkeypatch.setattr(ac, "_first_unsafe", spy_)
    hx = CX - 6.5
    ctx = ac.Ctx(b_iid=7, b_x=CX, b_y=cs.FLOOR + 4.434, b_face=-1, kb0=9, a_box=None, hero_x=hx, face=1, tls=ac.timelines())
    assert ac.search(sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0), ctx, stages=sp.AS_STAGES, strict=True) is not None
    assert seen and all(o is not None and (o[:, 1] == 1).all() for o in seen)
    seen.clear()
    assert ac.search(sim_for(hx, f=1001, ground=False, bb=6.0, vy=2.0), ctx, stages=sp.AS_STAGES) is not None
    assert seen and all(o is None for o in seen)


@pytest.mark.parametrize("used", [False, True])
def test_the_runs_wait_shares_the_slam_budget(monkeypatch, no_plan, used):
    # the playbook's own run (step: late in the air -> _cs_try -> the air catch) reads the same slam record: with its budget
    # used up (by air_catch_try or earlier looks) no search
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    monkeypatch.setattr(cs, "CLAWSTRIKE", False)
    hx = CX - 6.5
    p = sp.SlamPlay(sp.PlayCfg())
    if used:
        p._as_slams[7] = {"ta": 10.0 - 30 / 60.0, "fails": sp.AS_FAIL_MAX, "next_t": float("-inf")}
    p.step(1000, air(1000, 32, hx), False, t_game=10.0, sim=sim_for(hx, ground=False, bb=6.0))
    assert p.run is not None and p.run.why == "late"
    assert no_plan == ([] if used else [(sp.AS_STAGES, True)])


# ---- Sol seq367: the committed continuation runs the plan it verified (no press-made protection, the sent state bound) ----

PAD_A = (33.26, 3.02, 36.85, 6.92)
EVERYWHERE = (-100.0, -100.0, 200.0, 200.0)


def pad_scene():
    """The pad (垫刀) scene: her 4.2 u up at x 35 falling (vy -10) over A's body, B (S, iid 8) at x 44 facing her in its antic
    (frame 5 at the STATE frame 1000)."""
    S = kin.initial_state(PARAMS, 35.0, cs.FLOOR + 4.2 + cs.POS_DY, vy=-10.0, facing=1, ground=False)
    sim = ac.ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERR, 1000, 1000)
    ctx = ac.Ctx(b_iid=8, b_x=44.0, b_y=7.449, b_face=-1, kb0=5, a_box=PAD_A, hero_x=35.0, face=1, tls=ac.timelines())
    return sim, ctx


@pytest.fixture(scope="module")
def pad():
    """The air catch's plan in the pad scene (strict, the 47 stage): a down slash pressed at 1002 meets A at 1005, the strike
    pressed at 1042 meets B at 1048."""
    sim, ctx = pad_scene()
    return sim, ctx, ac.search(sim, ctx, stages=sp.AS_STAGES, strict=True)


def after_press(sim, ctx, p, fo2, bounce_at=None, pogo=None, a_box=None):
    """A later tick of the pad plan with its down slash sent (pressed_down). fo2 == sim.fo: STATE frame fo2 + 1, the press in
    the masks in flight (sim's own, then the plan's mask of the press). Else STATE frame fo2: the start rolled with the plan's
    keys (its bounce at bounce_at when given), the prefix the plan's mask of fo2 + 1; pogo: the observed protection
    (POGO_OBS) with the model's own INV_T cleared - the tracker's start state after a real bounce."""
    q = ac.Plan(**{k: getattr(p, k) for k in p.__dataclass_fields__})
    q.pressed_down = q.f_down
    if fo2 == sim.fo:
        f2, S2, hold = fo2 + 1, sim.start, sim.hold
        pre = np.array(list(sim.prefix) + [ac.mask_at(p, F) for F in range(sim.f + 2, fo2 + 3)], np.int64)
    else:
        f2, F0 = fo2, sim.f + 2
        cm = ac.plan_cmds(p, F0, p.f_press - F0 + 40)[None, :fo2 - F0 + 1]
        ev = None
        if bounce_at is not None:
            ev = np.zeros_like(cm)
            ev[0, bounce_at - F0] = kin.EV_POGO
        S2, hold = sim.roll(cm, ev).final[:, 0].copy(), kin.HoldState.idle(1)
        if pogo is not None:
            S2[kin.INV_T], S2[kin.POGO_OBS] = 0.0, float(pogo)
        pre = np.array([ac.mask_at(q, fo2 + 1)], np.int64)
    sim2 = ac.ChainSim(S2, pre, hold, PARAMS, TERR, fo2, f2)
    ctx2 = ac.Ctx(b_iid=ctx.b_iid, b_x=ctx.b_x, b_y=ctx.b_y, b_face=ctx.b_face, kb0=ctx.kb0 + (fo2 - sim.fo),
                  a_box=ctx.a_box if a_box is None else a_box, hero_x=float(S2[kin.PX]), face=ctx.face, tls=ctx.tls)
    return sim2, ctx2, q


def hammer_at(monkeypatch, fo, frames):
    """B's hammer box over everything on the given STATE frames (the sim's rollout index + fo)."""
    real = ac._b_boxes

    def fake(ctx, tl, idx, which):
        out = real(ctx, tl, idx, which)
        if which == "hammer":
            out = np.array(out, float)
            out[np.isin(np.asarray(idx) + fo, frames)] = EVERYWHERE
        return out
    monkeypatch.setattr(ac, "_b_boxes", fake)


def test_pad_scene_plan(pad):
    sim, ctx, p = pad
    assert (p.f_down, p.c_down, p.f_press, p.c_strike, p.k_press, p.f_umb) == (1002, 1005, 1042, 1048, 47, 1010)


@pytest.mark.parametrize("fo2", [1000, 1002, 1003, 1004])
def test_a_sent_slash_not_yet_hit_is_modelled_from_the_real_prefix(pad, fo2):
    # Sol seq367 (normal re-pogo goes on): the sent down slash not yet hit - its press in flight (1000), its swing in the start
    # state (1002, 1003), its contact in flight (1004: ev_pre) - meets A on the same frame as planned and the strike follows;
    # no protection is made from the press (inv_until stays None)
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, fo2)
    v = ac.verify(sim2, ctx2, q, strict=True)
    assert v is not None and (v.c_down, v.c_strike, v.inv_until, q.inv_until) == (1005, 1048, None, None)


def test_a_contact_frame_without_observed_protection_is_still_pending(pad):
    # the start state on the planned contact frame (1005) with no observed protection (the game's bounce not seen): the contact
    # is predicted from the next frame on (1006), never on frames before the start state
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1005)
    assert not ac._sent_down_bounced(sim2, q)
    v = ac.verify(sim2, ctx2, q, strict=True)
    assert v is not None and v.c_down == 1006


def test_the_historical_check_is_unchanged(pad):
    # not strict (the Clawline's strike, SP10b): the historical rule - no pending contact modelled, the press-made window - as
    # before this package (here the plan fails it right after the press: no bounce in its model)
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1002)
    assert not ac.check(sim2, ctx2, q) and ac.verify(sim2, ctx2, q) is None and ac.check(sim2, ctx2, q, strict=True)


def test_the_hazard_path_carries_the_bounce_in_flight(pad):
    # plan_path (the known-hazard check's path) places a pending contact in the masks in flight as evaluate does: from the tick
    # 1004 (contact 1005 in flight) her box rises after the bounce
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1004)
    v = ac.verify(sim2, ctx2, q, strict=True)
    xs, bottom = ac.plan_path(sim2, v)
    assert v.c_down == 1005 and bottom[3] > bottom[2] + 0.2                  # frames 1007 vs 1006


@pytest.mark.parametrize("top,ok", [(6.92, True), (7.0, False)])
def test_a_sent_slash_before_its_contact_a_body(pad, top, ok):
    # Sol seq367 minimum (pressed, not hit, F_INVULN 0): A's body over her box from 1002 (top 7.0) is reported; the contact on A
    # (1005) clears only its own 2 frames before it (1003, 1004: the target rule PRE 2 - top 6.92 passes). A press-made window
    # (inv_until press + 19, the historical rule) no longer hides it under strict
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1000, a_box=(PAD_A[0], PAD_A[1], PAD_A[2], top))
    assert (ac.verify(sim2, ctx2, q, strict=True) is not None) == ok
    q.inv_until = q.pressed_down + ac.ACTIVE[1] + 10
    assert bool(ac.evaluate(sim2, ctx2, [q], sim2.f + 2, strict=True)) == ok


@pytest.mark.parametrize("fo2,frame,ok", [(1002, 1003, False), (1002, 1004, False), (1002, 1006, True), (1004, 1006, True),
                                          (1000, 1002, False)])
def test_a_sent_slash_before_its_contact_b_hammer(monkeypatch, pad, fo2, frame, ok):
    # Sol seq367 minimum: B's hammer over her box before the pending contact (1002 - 1004; the target's 2 frames never clear B's
    # hammer) is reported; after the modelled bounce (1006) its i-frames cover it, the contact in flight (1004) too
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, fo2)
    hammer_at(monkeypatch, sim2.fo, [frame])
    assert (ac.verify(sim2, ctx2, q, strict=True) is not None) == ok


@pytest.mark.parametrize("frame,ok", [(None, True), (1008, True), (1016, False)])
def test_a_real_bounce_uses_the_observed_protection(monkeypatch, pad, frame, ok):
    # the down slash hit (1005): the start state 1006 carries the bounce and the observed protection (POGO_OBS 7, no model
    # INV_T): no second contact is predicted, a hammer inside the observed protection passes, one after it is reported
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1006, bounce_at=1005, pogo=7)
    assert ac._sent_down_bounced(sim2, q)
    if frame is not None:
        hammer_at(monkeypatch, sim2.fo, [frame])
    v = ac.verify(sim2, ctx2, q, strict=True)
    assert (v is not None) == ok
    assert v is None or (v.c_down is None and v.c_strike is not None)


def test_an_older_bounces_protection_is_not_this_press(pad):
    # POGO_OBS before this press's earliest contact (press + ACTIVE[0]) is an older bounce's: the slash stays pending (its
    # contact modelled); from that frame on it is this press's bounce
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1004)
    sim2.start[kin.POGO_OBS] = 5.0
    assert not ac._sent_down_bounced(sim2, q)
    v = ac.verify(sim2, ctx2, q, strict=True)
    assert v is not None and v.c_down == 1005
    sim3, _, _ = after_press(sim, ctx, p, 1005, bounce_at=1005, pogo=8)
    assert ac._sent_down_bounced(sim3, q)


def test_the_bound_re_search_keeps_the_sent_slash(monkeypatch, pad):
    # Sol seq367: the committed re-search binds the sent state first - every candidate evaluated carries the sent down slash
    # (no new one searched), the strike ATK_CD_F after its press, the umbrella after its Down hold; its plan is the one checked
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1003)
    seen = []
    real = ac.evaluate

    def spy_(sim_, ctx_, plans, F0, **kw):
        seen.extend(plans)
        return real(sim_, ctx_, plans, F0, **kw)
    monkeypatch.setattr(ac, "evaluate", spy_)
    monkeypatch.setattr(ac, "_down_candidates", lambda *a: pytest.fail("a new down slash searched"))
    got = ac.search(sim2, ctx2, stages=sp.AS_STAGES, strict=True, sent=q)
    assert seen and all((c.f_down, c.pressed_down) == (1002, 1002) for c in seen)
    assert all(c.f_press >= 1002 + ac.ATK_CD_F and (c.f_umb is None or c.f_umb > 1006) for c in seen)
    assert got is not None and (got.f_down, got.pressed_down, got.c_down) == (1002, 1002, 1005)
    assert got in seen and ac.verify(sim2, ctx2, got, strict=True) is not None


def test_the_bound_re_search_with_the_contact_in_flight(pad):
    # the tick 1004 (the pending contact 1005 in the masks in flight): the bound plan with no umbrella reaches its strike only
    # on that bounce (evaluate's strike pass and safety pass both carry it)
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1004)
    got = ac.search(sim2, ctx2, stages=sp.AS_STAGES, strict=True, sent=q)
    assert got is not None and (got.f_umb, got.c_down, got.c_strike, got.pressed_down) == (None, 1005, 1046, 1002)


def test_a_bound_re_search_needs_the_strike_atk_cd_after_the_sent_press(monkeypatch, pad):
    # a sent press too close to the strike (1030: the strike 1042 < 1030 + ATK_CD_F) leaves no candidate
    sim, ctx, p = pad
    sim2, ctx2, q = after_press(sim, ctx, p, 1003)
    q.f_down = q.pressed_down = 1030
    seen = []
    real = ac.evaluate
    monkeypatch.setattr(ac, "evaluate", lambda sim_, ctx_, plans, F0, **kw: seen.extend(plans) or real(sim_, ctx_, plans, F0, **kw))
    assert ac.search(sim2, ctx2, stages=sp.AS_STAGES, strict=True, sent=q) is None and seen == []


def test_the_committed_re_search_takes_a_bound_plan(monkeypatch, pad):
    # the normal continuation through the re-search: the committed plan no longer passing (here its drift cut short), the bound
    # re-search's plan keeps the sent slash and runs (the slash's Down still held), the budget untouched
    sim, ctx, p0 = pad
    sim2, ctx2, q = after_press(sim, ctx, p0, 1003)
    q.d_end, q.f_umb = 1004, None
    assert ac.verify(sim2, ctx2, q, strict=True) is None
    p, r, t = pad_run(monkeypatch, q, 1003)
    m = p.step(1003, pad_state(1003, float(sim2.start[kin.PX])), False, t_game=t, sim=sim2)
    new = r.cs_strike
    assert p.run is r and new is not q and (new.f_down, new.pressed_down, new.c_down) == (1002, 1002, 1005)
    assert r.cs_log[-1][1] == "restrike" and m == ac.mask_at(new, 1005) and m & ac.M_D and p._as_slams[8]["fails"] == 0


def pad_state(f, hx):
    """STATE of frame f in the pad scene: S (iid 8) at x 44 in Slam Antic at its antic frame 5 + (f - 1000), A (iid 9) Idle
    with its body collider PAD_A, her at x hx in the air facing right."""
    s = state(f, "Slam Antic", (5 + f - 1000) / 60.0, cx=44.0, hx=hx, ground=False, iid=8)
    s["ents"][0]["pos"] = [44.0, 7.449]
    x0, y0, x1, y1 = PAD_A
    s["ents"].append({"type_key": sp.CLAPPER, "iid": 9, "hp": 200, "pos": [35.0, 7.45], "flipX": False,
                      "fsms": [{"name": "Control", "state": "Idle", "t": 0.3}],
                      "colliders": [{"name": sp.CLAPPER, "enabled": True, "verts_world": [x0, y0, x1, y0, x1, y1, x0, y1]}]})
    s["hero"]["facing"] = 1
    return s


def pad_run(monkeypatch, q, f):
    """SlamPlay holding the committed air catch on S (cs_strike) with the pad plan q (its down slash sent)."""
    monkeypatch.setattr(cs, "AIRSTRIKE", True)
    p = sp.SlamPlay(sp.PlayCfg())
    t = t_of(f)
    r = sp.Run(iid=8, fa=995, face=-1, ta=t - (5 + f - 1000) / 60.0)
    r.phase, r.as_air, r.cs_strike, r.hp0, r.k_start = "cs_strike", True, q, 9, 5
    p.run = r
    return p, r, t


def test_the_committed_continuation_runs_the_plan_it_verified(monkeypatch, pad):
    # Sol seq367 (the normal continuation kept; _as_hazard's order): the tick after the press, the committed plan with its sent
    # slash is verified as it is, the known hazards read on that verified copy (this tick's contacts), its contacts kept on the
    # committed plan, no search; the keys hold the slash's Down and the drift
    sim, ctx, p0 = pad
    sim2, ctx2, q = after_press(sim, ctx, p0, 1002)
    p, r, t = pad_run(monkeypatch, q, 1002)
    q.c_down = q.c_strike = None                              # stale contacts: replaced by this tick's
    seen = []
    real = sp.SlamPlay._as_hazard

    def spy_(self, r_, s_, e_, plan, sim_, t_, k_):
        seen.append((plan is q, plan.c_down, plan.c_strike))
        return real(self, r_, s_, e_, plan, sim_, t_, k_)
    monkeypatch.setattr(sp.SlamPlay, "_as_hazard", spy_)
    monkeypatch.setattr(ac, "search", lambda *a, **k: pytest.fail("searched"))
    m = p.step(1002, pad_state(1002, float(sim2.start[kin.PX])), False, t_game=t, sim=sim2)
    assert p.run is r and r.cs_strike is q and seen == [(False, 1005, 1048)] and (q.c_down, q.c_strike) == (1005, 1048)
    assert m == ac.mask_at(q, 1004) and m & ac.M_D and m & ac.M_R


@pytest.mark.parametrize("hazard", [False, True])
def test_the_committed_re_search_is_bound_and_runs_as_checked(monkeypatch, pad, hazard):
    # Sol seq367 minimum: the old slash sent and not hit, the committed plan failing its verify: the re-search gets the sent
    # state (sent = the committed plan) and its plan runs as returned - nothing moved into it after its check (the old
    # transplant wrote the old f_down / pressed_down into a plan checked without them); a known hazard on that plan: not taken,
    # the failure counted, the press far: the run ends
    sim, ctx, p0 = pad
    sim2, ctx2, q = after_press(sim, ctx, p0, 1002)
    p, r, t = pad_run(monkeypatch, q, 1002)
    cand = ac.Plan(1004, ac.M_R, 1010, None, None, 1042, 47, 8, c_down=None, c_strike=1048)
    got, hz = [], []
    monkeypatch.setattr(ac, "verify", lambda sim_, ctx_, plan, strict=False: None)
    monkeypatch.setattr(ac, "search", lambda sim_, ctx_, stages=None, strict=False, sent=None: got.append(sent) or cand)
    monkeypatch.setattr(sp.SlamPlay, "_as_hazard", lambda self, r_, s_, e_, plan, *a: hz.append(plan) or ("x" if hazard else None))
    m = p.step(1002, pad_state(1002, float(sim2.start[kin.PX])), False, t_game=t, sim=sim2)
    assert got == [q] and hz == [cand] and (cand.f_down, cand.pressed_down) == (None, None)
    if hazard:
        assert m is None and p.run is None and p.done[-1].why == "as no strike" and p._as_slams[8]["fails"] == 1
    else:
        assert p.run is r and r.cs_strike is cand and m == ac.mask_at(cand, 1004)


@pytest.mark.parametrize("st,kept", [("Idle", True), ("Jump Antic", False)])
def test_the_kept_plan_still_reads_the_known_hazards(monkeypatch, pad, st, kept):
    # SP13a's keep (its strike close, no plan verified, unchanged): the committed plan goes on unless a known hazard is there
    sim, ctx, p0 = pad
    sim2, ctx2, q = after_press(sim, ctx, p0, 1002)
    p, r, t = pad_run(monkeypatch, q, 1002)
    q.f_press = 1010                                          # its strike within KEEP_F of this tick's mask frame (1004)
    monkeypatch.setattr(ac, "verify", lambda sim_, ctx_, plan, strict=False: None)
    monkeypatch.setattr(ac, "search", lambda sim_, ctx_, stages=None, strict=False, sent=None: None)
    s = pad_state(1002, float(sim2.start[kin.PX]))
    s["ents"][1]["fsms"][0]["state"] = st
    m = p.step(1002, s, False, t_game=t, sim=sim2)
    if kept:
        assert p.run is r and r.cs_strike is q and r.cs_log[-1][1] == "keep" and m == ac.mask_at(q, 1004)
    else:
        assert m is None and p.run is None and p.done[-1].why == "as hazard"


def test_the_committed_plan_failing_with_no_bound_plan_ends(monkeypatch, pad):
    # B's hammer over her on the next commanded frame (1004, before the pending contact): the committed plan fails, no bound
    # plan passes, the press far (no keep): the run ends, the planner decides - no unchecked keys sent
    sim, ctx, p0 = pad
    sim2, ctx2, q = after_press(sim, ctx, p0, 1002)
    p, r, t = pad_run(monkeypatch, q, 1002)
    hammer_at(monkeypatch, sim2.fo, [1004])
    m = p.step(1002, pad_state(1002, float(sim2.start[kin.PX])), False, t_game=t, sim=sim2)
    assert m is None and p.run is None and p.done[-1].why == "as no strike" and p._as_slams[8]["fails"] == 1
