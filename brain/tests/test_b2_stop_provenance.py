"""Known B2 stops keep their primary; all later shell failures remain evidence."""
import json
from types import SimpleNamespace
import pytest
from ssbot.combat.knife_chain_budget import LearningStop,mark_integrity_halt,preflight_environment
from ssbot.tools import combat_run as C
from tests.test_b2_worker_batch import Rig,env,options
from tests.test_b2_worker_audit_priority import STOP,REASON


def test_different_episode_failure_survives_as_secondary_to_known_stop():
    got=C._b2_stop_details(REASON,STOP,REASON,outcome="HARNESS_FAIL",episode_reason="TimeoutError: new episode callback timeout")
    assert got["reason"]==REASON and got["origin"]=="chain.learning_stop"
    assert got["secondary_errors"]==[{"origin":"episode.exception","reason":"TimeoutError: new episode callback timeout"}]


@pytest.mark.parametrize("reported",[REASON,"LearningStop: "+REASON])
def test_same_stop_wrapper_is_not_an_invented_second_fault(reported):
    got=C._b2_stop_details(REASON,STOP,REASON,outcome="HARNESS_FAIL",episode_reason=reported)
    assert got["reason"]==REASON and got["secondary_errors"]==[]


def test_halt_first_reason_is_original_stop_and_existing_marker_is_immutable(tmp_path,monkeypatch):
    env(monkeypatch,tmp_path)
    mark_integrity_halt("measurement incomplete",primary=REASON,primary_origin="chain.learning_stop",secondary_origin="measurement")
    path=tmp_path/"budget.json.halt";first=path.read_bytes();marker=json.loads(first)
    assert marker["reason"]==REASON and marker["primary_error_origin"]=="chain.learning_stop"
    assert marker["secondary_errors"]==[{"origin":"measurement","reason":"measurement incomplete"}]
    mark_integrity_halt("later cleanup error",primary="a different claimed stop",secondary_origin="cleanup")
    assert path.read_bytes()==first
    with pytest.raises(LearningStop,match="integrity halt"):preflight_environment("Forum_W_w7")


def test_returned_new_harness_failure_is_saved_in_attempt_cleanup_and_marker(tmp_path,monkeypatch):
    rig=Rig(tmp_path,monkeypatch,fault="injury")
    from ssbot.train import episode as E
    original=E.run_episode
    def wrapped(link,enc,tap,policy,cfg,record):
        original(link,enc,tap,policy,cfg,record)
        policy.chain_native.learning_stop=REASON
        record.reason="TimeoutError: new release callback failed"
    monkeypatch.setattr(E,"run_episode",wrapped)
    assert rig.run(episodes=1)==0
    data=json.loads((tmp_path/"attempts_i0.jsonl").read_text().splitlines()[0])
    assert data["outcome"]=="HARNESS_FAIL" and data["reason"]=="TimeoutError: new release callback failed"
    assert data["b2_learning_stop"]==REASON
    fault={"origin":"episode.exception","reason":"TimeoutError: new release callback failed"}
    assert fault in data["secondary_errors"] and fault in rig.receipts()[0]["secondary_errors"]
    marker=json.loads((tmp_path/"budget.json.halt").read_text())
    assert marker["reason"]==REASON and fault in marker["secondary_errors"]
    assert rig.budget.state["b_fight_hp"]==2 and len(rig.budget.state["attempts"])==1
    assert rig.links[0].closed and rig.events.count("ready")==1


def test_unreturned_episode_finally_failure_recovers_existing_stop_and_both_new_faults(tmp_path,monkeypatch):
    rig=Rig(tmp_path,monkeypatch,fault="injury")
    from ssbot.train import episode as E
    original=E.run_episode
    def wrapped(link,enc,tap,policy,cfg,record):
        original(link,enc,tap,policy,cfg,record)
        policy.chain_native.learning_stop=REASON
        record.reason="TimeoutError: episode callback already failed"
        raise OSError("later episode summary failed")
    monkeypatch.setattr(E,"run_episode",wrapped)
    with pytest.raises(LearningStop,match="B fight cumulative 2 HP") as caught:rig.run(episodes=1)
    assert isinstance(caught.value.__cause__,OSError)
    cleanup=rig.receipts()[0]
    assert cleanup["primary_error"]=="LearningStop: "+REASON and cleanup["primary_error_origin"]=="chain.learning_stop"
    assert {"origin":"episode.exception","reason":"TimeoutError: episode callback already failed"} in cleanup["secondary_errors"]
    assert {"origin":"worker.exception","reason":"OSError: later episode summary failed"} in cleanup["secondary_errors"]
    marker=json.loads((tmp_path/"budget.json.halt").read_text())
    assert marker["reason"]==REASON
    assert {"origin":"worker.exception","reason":"OSError: later episode summary failed"} in marker["secondary_errors"]
    assert rig.budget.state["b_fight_hp"]==2 and len(rig.budget.state["attempts"])==1 and rig.links[0].closed


def test_cleanup_only_failure_keeps_existing_primary_first_in_marker(tmp_path,monkeypatch):
    env(monkeypatch,tmp_path)
    class Broken:
        def close(self):raise OSError("secondary close failure")
    result=C._close_worker(options(tmp_path),link=None,recorder=Broken(),out=None,diagnostics=None,policy=None,
       stage="episodes",primary_error="LearningStop: "+REASON,primary_error_origin="budget.stop")
    marker=json.loads((tmp_path/"budget.json.halt").read_text())
    assert marker["reason"]=="LearningStop: "+REASON and marker["primary_error_origin"]=="budget.stop"
    assert marker["secondary_errors"][0]["origin"]=="cleanup" and "secondary close failure" in marker["secondary_errors"][0]["reason"]
    assert result["complete"] is False and result["primary_error"]=="LearningStop: "+REASON


def test_original_episode_outcome_and_window_incomplete_are_not_reclassified(monkeypatch):
    from ssbot.train import episode as E
    record=E.AttemptRecord(unit="Forum_W_w7",stage="TRAIN",profile="TRAIN",build="test",code_rev="test",
       config_fp="test",start_kind="savestate",mode="eval",seed=1,f_reset=1000,b2_context={})
    finishes=[]
    window=SimpleNamespace(complete=False,finish_at=lambda *a:finishes.append(a))
    measurement=SimpleNamespace(window=window,_last_frame=1001)
    link=SimpleNamespace(frame=1001,state={},measurement=measurement,act=lambda *a,**k:None,rpc=lambda *a,**k:None)
    policy=SimpleNamespace(chain_native=SimpleNamespace(learning_stop=REASON))
    def fail(*a):raise TimeoutError("new episode shell failure")
    monkeypatch.setattr(E,"_run",fail);monkeypatch.setattr(E,"_summarise",lambda *a:None)
    E.run_episode(link,None,None,policy,None,record)
    assert record.outcome==E.HARNESS_FAIL and record.reason=="TimeoutError: new episode shell failure"
    assert window.complete is False and finishes==[(1001,"episode_harness_fail")]
    details=C._b2_stop_details(policy.chain_native.learning_stop,STOP,REASON,outcome=record.outcome,episode_reason=record.reason)
    assert details["reason"]==REASON and details["secondary_errors"][0]["origin"]=="episode.exception"
