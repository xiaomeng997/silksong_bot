"""Episode HP floor uses the existing pause/quit path; integrity still stops batch."""
import json
from types import SimpleNamespace as NS
import pytest
from ssbot.combat.knife_chain_budget import LearningBudget,LearningStop,preflight_options,execution_conditions
from ssbot.safety.supervisor import Supervisor,SupervisorConfig,SupervisorInput,Q1_HIT
from ssbot.safety.hits_to_death import SupportEvent,MASK_NONE

LOW="episode-remaining-2hp-v1"


def budget(path,**kw):
    return LearningBudget(path,batch="new",revision="new-rule",worker="i0",policy=LOW,**kw)


def test_new_policy_accounts_injuries_and_continues_to_next_reserved_episode(tmp_path):
    b=budget(tmp_path/"budget.json");b.bind_execution({"real_quit":1.})
    b.begin_attempt(episode=0,arm="B",seed=1)
    for f in (10,20,30):b.observe(episode=0,frame=f,arm="B",hp_loss=2,chain_related=True)
    assert b.state["b_fight_hp"]==6 and b.state["stop"] is None
    b.begin_attempt(episode=1,arm="B",seed=2)
    assert len(b.state["events"])==3 and len(b.state["attempts"])==2
    assert b.state["policy"]==LOW and b.remaining_hp_quit==2


@pytest.mark.parametrize("fatal",["death","key application desync","missing critical log"])
def test_integrity_stop_is_still_latched_and_never_advanced(tmp_path,fatal):
    b=budget(tmp_path/"budget.json");b.bind_execution({"real_quit":1.})
    with pytest.raises(LearningStop,match=fatal):b.observe(episode=0,frame=10,arm="B",fatal=fatal)
    before=b.path.read_bytes()
    with pytest.raises(LearningStop):b.begin_attempt(episode=1,arm="B",seed=2)
    assert b.path.read_bytes()==before


@pytest.mark.parametrize("first_new",[False,True])
def test_new_rule_never_reinterprets_an_existing_strict_ledger(tmp_path,first_new):
    p=tmp_path/"b.json"
    if first_new:old=budget(p)
    else:old=LearningBudget(p,batch="new",revision="new-rule",worker="i0")
    before=p.read_bytes()
    with pytest.raises(LearningStop,match="NEW batch|identity"):
        if first_new:LearningBudget(p,batch="new",revision="new-rule",worker="i0")
        else:budget(p)
    assert p.read_bytes()==before


def test_legacy_stop_and_marker_cannot_be_reopened_under_new_rule(tmp_path):
    p=tmp_path/"b.json";old=LearningBudget(p,batch="new",revision="new-rule",worker="i0")
    with pytest.raises(LearningStop):old.observe(episode=0,frame=10,arm="B",hp_loss=2)
    before=p.read_bytes()
    with pytest.raises(LearningStop):budget(p)
    assert p.read_bytes()==before and p.with_name(p.name+".created").exists()


@pytest.mark.parametrize("hp",[1,2,3,5])
def test_raw_hp_floor_is_exact_and_uses_existing_q1_hit_cause(hp):
    # Blue masks and a one-damage support keep h > 1: the literal HP floor must
    # still request Q1, rather than depend on the old hits-to-death heuristic.
    c=SupervisorConfig(worst_known_damage=1,remaining_hp_quit=2)
    sup=Supervisor(c)
    def inp(t,h):return SupervisorInput(t=t,hp=h,max_hp=7,blue=5,mask=MASK_NONE,
        support=(SupportEvent("body",1),),support_known=True,plan_s=0,hurt=True)
    sup.step(inp(0.,7));d=sup.step(inp(.02,hp))
    assert ("Q1" in d.triggers)==(hp<=2)
    if hp<=2:
        assert d.pause_pending and d.quit_requested and d.q1_cause==Q1_HIT
        assert any("remaining HP" in x for x in d.reasons)


def test_unrelated_supervisor_has_no_new_hp_floor():
    assert SupervisorConfig(worst_known_damage=1).remaining_hp_quit is None


def test_new_execution_profile_binds_quit_policy_and_rejects_emulated_or_random_quit(tmp_path,monkeypatch):
    from tests.test_b2_worker_batch import options,env
    env(monkeypatch,tmp_path)
    for prob in (0.,.5):
        with pytest.raises(LearningStop):preflight_options(options(tmp_path,real_quit=prob))
    a=options(tmp_path,real_quit=1.);preflight_options(a)
    conditions=execution_conditions(a)
    assert conditions["learning_policy"]=={"name":LOW,"remaining_hp":2,"scope":"episode","pause_then_real_quit":True}


def test_native_factory_selects_new_policy(tmp_path,monkeypatch):
    from ssbot.combat import knife_chain_b2 as B,knife_chain_slam as S,attack_range as A
    from tests.test_b2_worker_batch import env
    env(monkeypatch,tmp_path)
    monkeypatch.setattr(S,"load_runner",lambda:NS(cfg0={}))
    monkeypatch.setattr(A,"load_table",lambda **kw:NS(meta={"hammer_polygon_revision":1}))
    class Bare(B.NativeChainB2):
        def __init__(self,**kw):self.__dict__.update(kw)
    b=Bare.from_env(journal=str(tmp_path/"trace.jsonl"))
    assert b.budget.policy==LOW and b.budget.remaining_hp_quit==2


def test_new_floor_does_not_change_legacy_positional_config_arguments():
    c=SupervisorConfig(2,.35,7)
    assert c.q2_escape_s==.35 and c.q4_unpredicted_hits==7 and c.remaining_hp_quit is None


def test_real_worker_continues_after_accounted_loss_under_new_policy(tmp_path,monkeypatch):
    from tests import test_b2_worker_batch as T
    original=T.LearningBudget
    monkeypatch.setattr(T,"LearningBudget",lambda *a,**kw:original(*a,**kw,policy=LOW))
    rig=T.Rig(tmp_path,monkeypatch,fault="injury")
    assert rig.run(episodes=2)==0
    assert rig.attempts==2 and rig.budget.state["b_fight_hp"]==4 and rig.budget.state["stop"] is None
    assert len(rig.budget.state["attempts"])==2 and rig.events.count("ready")==2


def test_existing_real_quit_recovery_returns_to_slot_before_next_attempt(monkeypatch):
    from ssbot.tools import combat_run as C
    calls=[];link=NS();enc=NS()
    monkeypatch.setattr(C,"back_into_slot",lambda *a:calls.append(a))
    C.after_episode(link,enc,0,{"outcome":"QUIT","policy":{"real_quit":{"main_menu":True}}})
    assert calls==[(link,enc,0)]
