"""Optional precision is independent of the corrected hammer damage clock."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import observed_slam as O, attack_range as A, forum_planner as F
from tests.test_forum_planner import params, arena, _with_collider, _world, _reed_forecaster, _prefs, _ctx, FLOOR


def switches(monkeypatch, master=True, stop=False, finite=False):
    monkeypatch.setattr(O, "ENABLED", master)
    monkeypatch.setattr(O, "MOTION_ENABLED", stop, raising=False)
    monkeypatch.setattr(O, "FINITE_ENABLED", finite, raising=False)


@pytest.mark.parametrize("master,stop,finite", [(a,b,c) for a in (False,True) for b in (False,True) for c in (False,True)])
def test_tracker_has_no_optional_work_when_subfeatures_are_off(monkeypatch, master, stop, finite):
    switches(monkeypatch,master,stop,finite)
    tr=A.RangeTracker({})
    assert (tr.observed_motion is not None) == (master and (stop or finite))
    fields=O.revision_fields()
    assert fields["observed_slam_motion"] == (master and stop)
    assert fields["observed_slam_finite"] == (master and finite)
    assert fields["observed_slam"] == master


def test_disabling_motion_ignores_a_preexisting_stop_in_support_and_certain_body(monkeypatch):
    from tests.test_observed_slam_integration import tracker
    switches(monkeypatch,stop=True)
    tr,tab=tracker(monkeypatch,True)
    assert tr.observed_stop(1) is not None
    targets=[NS(iid=1,hazard=False)]
    box=np.tile(np.array([[[27.,3.,31.,7.]]]),(1,13,1))
    frozen=F.ForumPlanner._ds_move_paths(tr,targets,box)
    switches(monkeypatch,stop=False)
    assert tr.observed_stop(1) is None
    masks={k:tr.estimate(1,k).raw for k in (0,1,12)}
    moving=F.ForumPlanner._ds_move_paths(tr,targets,box)
    assert not np.array_equal(moving[0][0],frozen[0][0])
    tr.observed_motion.by_iid.clear()
    reference=F.ForumPlanner._ds_move_paths(tr,targets,box)
    np.testing.assert_array_equal(moving[0][0],reference[0][0])
    for k,m in masks.items():
        ref=tr.estimate(1,k).raw
        np.testing.assert_array_equal(m.m,ref.m)
        assert (m.ix0,m.iy0)==(ref.ix0,ref.iy0)


def test_clock_layer_survives_both_optional_switches_off(monkeypatch):
    from tests.test_slam_damage_clock import table, cells
    switches(monkeypatch)
    tab,tp=table(gated=True)
    assert len(cells(tab.place("CC_SLAM","main",2,(8.,5.),1,now=(10.,5.),b_now=1,st_now="Slam 2")))==4
    assert len(cells(tab.place("CC_SLAM","main",2,(8.,5.),1,now=(10.,5.),b_now=2,st_now="Slam Recover")))==1


@pytest.mark.parametrize("finite",[False,True])
def test_real_forced_planner_dispatches_expiry_only_for_explicit_finite_opt_in(monkeypatch,params,arena,finite):
    switches(monkeypatch,finite=finite)
    calls=[]
    def expiry(ws,forecast,**kw):
        calls.append(ws.stamp.frame)
        return np.full(len(F.seen_polys(ws)[2]),.1)
    monkeypatch.setattr(O,"seen_expiries",expiry)
    forced=0
    for x in (30.6,31.0,31.6):
        ws=_with_collider(_world(x),(x+4.,FLOOR,x+5.5,FLOOR+2.),-18.)
        mf=_reed_forecaster(10,frames=17)
        p=F.ForumPlanner(params,arena,F.PlannerConfig(T=36,threads=2,variants="bounds_lo"),
            F.ForumConfig(deadline_ms=math.inf,chunk=16,forced_rank="seen",commit_rank=False))
        r=p.tick(ws,F.kin.initial_state(params,x,FLOOR+params.foot),F.kin.HoldState.idle(1),
            np.zeros(1,np.int64),mf.forecast(.8),_prefs(),_ctx())
        forced+=int(r.forced_risk)
    assert forced>0
    assert bool(calls)==finite


def test_disabled_finite_does_not_prewarm_unused_kernel(monkeypatch):
    from ssbot.combat import seen_lifetime as L
    switches(monkeypatch)
    monkeypatch.setattr(F.Planner,"warm_kernels",lambda _:None)
    monkeypatch.setattr(F,"seen_contacts",lambda *a:None)
    monkeypatch.setattr(F,"seen_contacts_swept",lambda *a:None)
    def unwanted(*a):raise AssertionError("disabled finite kernel was called")
    monkeypatch.setattr(L,"timed_seen",unwanted)
    class Done(Exception):pass
    def next_kernel(*a):raise Done()
    monkeypatch.setattr(F,"pin_contacts_kernel",next_kernel)
    with pytest.raises(Done):F.ForumPlanner.warm_kernels(F.ForumPlanner.__new__(F.ForumPlanner))


@pytest.mark.parametrize("bad",["2","true",""])
def test_optional_environment_values_are_validated_at_import(bad):
    for name in ("SSBOT_FORUM_SLAM_STOP","SSBOT_FORUM_SLAM_FINITE"):
        env={**os.environ,name:bad,"PYTHONPATH":str(Path(__file__).resolve().parents[1])}
        r=subprocess.run([sys.executable,"-B","-c","from ssbot.combat import observed_slam"],env=env,capture_output=True,text=True)
        assert r.returncode!=0 and name in r.stderr


def test_optional_defaults_are_off_even_when_damage_clock_is_on():
    env={k:v for k,v in os.environ.items() if k not in {"SSBOT_FORUM_SLAM_STOP","SSBOT_FORUM_SLAM_FINITE"}}
    env.update(SSBOT_FORUM_OBSERVED_SLAM="1",PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    r=subprocess.run([sys.executable,"-B","-c","import json;from ssbot.combat.observed_slam import revision_fields;print(json.dumps(revision_fields()))"],env=env,capture_output=True,text=True,check=True)
    fields=json.loads(r.stdout)
    assert fields["observed_slam"] is True and fields["observed_slam_motion"] is False and fields["observed_slam_finite"] is False


@pytest.mark.parametrize("name",["MOTION_ENABLED","FINITE_ENABLED"])
def test_optional_switch_change_cannot_reuse_a_shared_learning_ledger(tmp_path,monkeypatch,name):
    from ssbot.combat import knife_chain_b2 as B,knife_chain_slam as S
    from ssbot.combat.knife_chain_budget import LearningStop
    switches(monkeypatch)
    monkeypatch.setattr(S,"load_runner",lambda:NS(cfg0={}))
    monkeypatch.setattr(A,"load_table",lambda **kw:NS(meta={"hammer_polygon_revision":1}))
    class Bare(B.NativeChainB2):
        def __init__(self,**kw):self.__dict__.update(kw)
    for k,v in {"SSBOT_FORUM_CHAIN_BATCH":"optional-profile","SSBOT_FORUM_CHAIN_ARM":"A",
                "SSBOT_FORUM_CHAIN_BUDGET":str(tmp_path/"ledger.json"),"SSBOT_FORUM_CHAIN_FAST_HOOK":"0"}.items():monkeypatch.setenv(k,v)
    Bare.from_env(journal=str(tmp_path/"a.jsonl"));before=(tmp_path/"ledger.json").read_bytes()
    monkeypatch.setattr(O,name,True)
    with pytest.raises(LearningStop,match="revision"):Bare.from_env(journal=str(tmp_path/"b.jsonl"))
    assert (tmp_path/"ledger.json").read_bytes()==before


@pytest.mark.parametrize("name,variable",[("SSBOT_FORUM_SLAM_STOP","MOTION_ENABLED"),("SSBOT_FORUM_SLAM_FINITE","FINITE_ENABLED")])
def test_new_switches_have_actual_runtime_manifest_bindings(tmp_path,monkeypatch,name,variable):
    from ssbot.train.forum_measure_manifest import configuration_manifest
    switches(monkeypatch)
    src=tmp_path/"ssbot"; (src/"combat").mkdir(parents=True)
    (src/"combat/observed_slam.py").write_bytes(Path(O.__file__).read_bytes())
    m=configuration_manifest(src,NS(chain_native=None),environ={"SSBOT_FORUM_OBSERVED_SLAM":"1",name:"0"},modules={"ssbot.combat.observed_slam":O})
    entry=m["switches"][name]
    assert entry["resolution"]=="runtime_binding" and entry["role"]=="control"
    assert entry["effective"]=={"ssbot.combat.observed_slam."+variable:False}


@pytest.mark.parametrize("key",["SSBOT_FORUM_SLAM_STOP","SSBOT_FORUM_SLAM_FINITE"])
def test_changing_optional_env_after_construction_is_unresolved(tmp_path,monkeypatch,key):
    from ssbot.train.forum_measure_manifest import configuration_manifest
    switches(monkeypatch)
    src=tmp_path/"ssbot";(src/"combat").mkdir(parents=True)
    (src/"combat/observed_slam.py").write_bytes(Path(O.__file__).read_bytes())
    initial={"SSBOT_FORUM_OBSERVED_SLAM":"1","SSBOT_FORUM_SLAM_STOP":"0","SSBOT_FORUM_SLAM_FINITE":"0"}
    policy=NS(chain_native=NS(_environment=tuple(initial.items())))
    m=configuration_manifest(src,policy,environ={**initial,key:"1"},modules={"ssbot.combat.observed_slam":O})
    assert key+": environment changed after construction" in m["unresolved"]
