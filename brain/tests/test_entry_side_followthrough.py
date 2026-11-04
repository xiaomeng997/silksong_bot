"""Requested first side hit uses ordinary physics/HF/safety, not an A override."""
from dataclasses import replace
from types import SimpleNamespace as NS
import math
import numpy as np
import pytest
from ssbot.combat import candidates, entry_side, forum_v2
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.combat.tactics.modes import EntryAttack, GoalPrefs, entry_attack_prefs
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _world, _reed_forecaster, params, arena
from tests.test_forum_v2 import _support_with


def prefs(kind="side", **kw):
    return entry_attack_prefs(GoalPrefs("RUSH", 28.0, {}, target=7,
        entry_attack=EntryAttack(7, kind, 8, "CC_SLAM", 12., 0.), **kw))


@pytest.mark.parametrize("posture", candidates.POSTURES)
def test_cached_variant_keeps_same_rows_core_and_all_other_keys(posture):
    cs, core = candidates.build_forum(36, posture, clash=True, waits=True)
    before = cs.cmd.copy()
    now = entry_side.immediate_set(cs)
    side = np.array([cs.first_names[i].startswith("ATTACK(side)") for i in cs.first])
    assert now.cmd.shape == before.shape and np.array_equal(cs.cmd, before)
    assert np.array_equal(now.cmd[core], before[core])
    assert np.array_equal(now.cmd[~side], before[~side])
    assert np.array_equal(now.cmd[:, 4:], before[:, 4:])
    assert np.array_equal(now.cmd & ~kin.B_ATTACK, before & ~kin.B_ATTACK)
    assert (now.cmd[side, :3] & kin.B_ATTACK).all() and not (now.cmd[side, 3] & kin.B_ATTACK).any()
    assert np.array_equal(now.prim_bits, cs.prim_bits) and np.array_equal(now.bind, cs.bind)
    assert all("entry-now" in now.name(i) for i in np.flatnonzero(side))


@pytest.mark.parametrize("change", ["stomp", "absent", "wrong_target", "no_hit", "bind", "zero_weight"])
def test_other_intents_do_not_request_side_priority(change):
    p = prefs()
    if change == "stomp": p = prefs("stomp")
    if change == "absent": p = replace(p, entry_attack=None)
    if change == "wrong_target": p = replace(p, target=9)
    if change == "no_hit": p = replace(p, no_hit=frozenset({7}))
    if change == "bind": p = replace(p, want_bind=True)
    if change == "zero_weight": p = replace(p, hit_kw={7:(0.,0.,0.,0.)})
    assert entry_side.target_of(p) is None


def test_rank_requires_new_target_side_contact_and_admitted_row():
    sc = dict(targets=[NS(iid=7), NS(iid=8), NS(iid=7, blocked=True)],
              first_t=np.array([0,0,1,0,0,2,0]), first_k=np.array([1,1,1,4,1,1,1]),
              first_f=np.array([8,4,2,2,-1,1,1]), hits=np.array([1,1,1,1,0,1,0]))
    admitted = np.array([True,False,True,True,True,True,True])
    assert entry_side.hit_times(sc,7,admitted,37).tolist() == [8,38,38,38,38,38,38]
    assert entry_side.hit_times(sc,None,admitted,37).tolist() == [38]*7


def test_ground_only_air_hit_cannot_be_promoted():
    sc = dict(targets=[NS(iid=7)], first_t=np.array([0,0]),first_k=np.array([1,1]),
              first_f=np.array([4,5]),hits=np.array([1,1]),sw_f=np.array([2,2]),sw_k=np.array([1,1]))
    flags = np.zeros((2,37),np.int64);flags[1,1] = kin.F_GROUND
    assert entry_side.hit_times(sc,7,np.ones(2,bool),37,ground_only=True,flags=flags).tolist()==[38,5]


def run(params, arena, *, arm="B", p=None, old=False, x=27.5, y=None, face=1, ctx=None, prefix=None, blocked=False, hold=None):
    pl = ForumPlanner(params, arena, PlannerConfig(T=36,threads=1,variants="bounds_lo"),
        ForumConfig(v2=True,deadline_ms=math.inf),crest=params.crest)
    pl.chain_native = NS(b2=True,arm=arm)
    if old: pl.fsets_entry_side = pl.fsets
    start = kin.initial_state(params,x,FLOOR+params.foot)
    start[kin.FACE] = face
    if y is not None:
        start[kin.PY] = y; start[kin.GROUND] = 0.
    mf = _reed_forecaster(None,x=30.)
    if not blocked:
        # Three actual-form past Alert observations with the hero in range:
        # Reed Will Defend is now known false under its unchanged stance model.
        from tests.test_multi_forecast import _ws, _ent
        from ssbot.core.worldstate import E
        for step in range(3):
            w = _ws(12+step,(12+step)/60.,[_ent(7,30.,FLOOR+1.,"Alert",flip=True,
                     box=(29.5,FLOOR,30.5,FLOOR+2.))],[])
            w.hero.pos = E((x,FLOOR+params.foot))
            mf.update(w)
    f = forum_v2.V2Forecast(mf.forecast(.8),_support_with([]))
    ws = _world(x)
    res = pl._ordinary_tick(ws,start,kin.HoldState.idle(1) if hold is None else hold,
        np.zeros(1,np.int64) if prefix is None else prefix,f,p or prefs(),ctx or _ctx())
    return pl,res


@pytest.mark.parametrize("face",[1,-1])
def test_actual_planner_sends_attack_now_with_all_normal_checks(params,arena,face):
    pl,res = run(params,arena,face=face)
    assert not res.S and not res.forced_risk
    assert res.mask & kin.B_ATTACK
    assert "entry-now" in res.name
    assert pl.last_info["env"][res.idx] and pl.audit.core_not_enveloped==0
    assert pl.last_info["entry_side"]["model_contact_offset"] is not None
    assert pl.last_info["entry_side"]["actual_hit"] is False


def test_old_first_piece_only_turns_this_tick(params,arena):
    pl,res = run(params,arena,old=True)
    assert not res.S and not res.forced_risk
    assert not (res.mask & kin.B_ATTACK)


@pytest.mark.parametrize("arm,kind",[("A","side"),("B","stomp")])
def test_a_or_stomp_retains_original_candidate_set(params,arena,arm,kind):
    pl,res = run(params,arena,arm=arm,p=prefs(kind))
    assert "entry_side" not in pl.last_info
    assert not any("entry-now" in n for n in pl.last_cs.first_names)


def test_attack_disallowed_still_cannot_send_it(params,arena):
    from ssbot.core.primitives import Prim
    ctx = _ctx();ctx.allowed_mask[int(Prim.ATTACK_SIDE)] = False
    pl,res = run(params,arena,ctx=ctx)
    assert not (res.mask & kin.B_ATTACK)


def test_guarded_target_does_not_get_blind_attack(params,arena):
    pl,res = run(params,arena,blocked=True)
    assert not (res.mask & kin.B_ATTACK)
    assert pl.last_info["entry_side"]["model_contact_offset"] is None


@pytest.mark.parametrize("x,y",[(32.5,None),(27.5,4.35)])
def test_left_and_air_contact_use_same_side_rows(params,arena,x,y):
    pl,res=run(params,arena,x=x,y=y)
    assert not res.S and not res.forced_risk and res.mask & kin.B_ATTACK
    assert pl.last_info["entry_side"]["model_contact_offset"] is not None


def test_far_target_approaches_without_pressing_a_missed_first_swing(params,arena):
    pl,res=run(params,arena,x=24.)
    assert not res.S and not res.mask & kin.B_ATTACK and res.mask & kin.B_RIGHT


def test_already_held_attack_does_not_fabricate_an_immediate_edge(params,arena):
    hold=kin.HoldState.idle(1)
    hold.latched[0,1]=hold.desired[0,1]=True
    hold.age[0,1]=2
    pl,res=run(params,arena,hold=hold,prefix=np.array([kin.B_ATTACK],np.int64))
    assert not res.S and not res.forced_risk
    assert not res.mask & kin.B_ATTACK  # release first; an unchanged held A cannot be a new hit


@pytest.mark.parametrize("height",[None,4.35])
def test_current_wanderer_crest_also_accepts_first_side_swing(arena,height):
    from pathlib import Path
    p=kin.HeroParams.load(Path(__file__).resolve().parents[2]/"knowledge/1.0.30000/kinematics/hero_wanderer_forum.json")
    pl,res=run(p,arena,y=height)
    assert not res.S and not res.forced_risk and res.mask & kin.B_ATTACK
    assert pl.last_info["entry_side"]["model_contact_offset"] is not None
