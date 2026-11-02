"""Missing combat HP stays fatal; an observed real-quit boundary is distinct."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_budget import LearningStop
from tests.test_knife_chain_air import raw


def observer():
    n=NativeManualAirChain(runner_factory=load_runner,probe_ref="exit-hp-test")
    s=raw(1000);s["game"]={"scene":"Hang_04"};n.observe_learning(s)
    return n


def test_actual_quit_boundary_then_absent_hero_preserves_last_hp():
    n=observer();n.exit_transition=True;s=raw(1001);s["hero"]["health"]=6;s["game"]={"scene":"Quit_To_Menu"}
    n.observe_learning(s)
    for f in (1002,1003):n.observe_learning({"f":f,"hero":None,"game":{"scene":None}})
    assert n._budget_hp==6 and n._last_budget_f==1003
    assert n.counts["b2_hp_loss"]==1 and n.counts["b2_exit_frame_no_hp"]==2 and n.learning_stop is None


@pytest.mark.parametrize("confirmed,marker,scene,hero",[
    (False,False,"Quit_To_Menu",None),
    (True,False,None,None),
    (True,False,"Hang_04",None),
    (True,False,"Hang_04",{}),
    (True,True,"Hang_04",None),
    (True,True,"Hang_04",{}),
    (False,True,None,None),
    (True,True,"Other_Battle",None),
])
def test_missing_hp_still_stops_without_exact_confirmed_exit_scope(confirmed,marker,scene,hero):
    n=observer()
    if marker:
        n.exit_transition=True;s=raw(1001);s["game"]={"scene":"Quit_To_Menu"};n.observe_learning(s)
    n.exit_transition=confirmed
    with pytest.raises(LearningStop,match="missing critical hero HP"):
        n.observe_learning({"f":1002,"game":{"scene":scene},"hero":hero})


def test_reset_drops_exit_permission_and_scene_boundary():
    n=observer();n.exit_transition=True;n._exit_scene_frame=1001;n.reset(1)
    assert n.exit_transition is False and n._exit_scene_frame is None


@pytest.mark.parametrize("path",["learning_check","_begin_chain_native"])
def test_both_real_policy_paths_publish_actual_confirmed_quit_state(path):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    class Policy(ForumPlannerPolicy):
        @property
        def real_quit_active(self):return True
    p=Policy.__new__(Policy);p._inbox=None;seen=[]
    audit=NS(b2=True,exit_transition=False,_episode_start=None)
    audit.begin=lambda *a:seen.append(audit.exit_transition)
    audit.observe_learning=lambda *a,**k:seen.append(audit.exit_transition)
    p.chain_native=audit;s={"f":100}
    if path=="learning_check":p.learning_check(s,NS(death_frame=None,lethal=False))
    else:p._begin_chain_native(s)
    assert seen==[True]
