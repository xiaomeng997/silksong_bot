"""Crossover metadata and worker/policy episode identity; no game or transport."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from ssbot.combat.knife_chain_budget import (LearningBudget,LearningStop,execution_conditions,
    attempt_labels,crossover_schedule)
from ssbot.train.episode import AttemptRecord,_bind_b2_episode
from tests.test_b2_worker_batch import options,Rig


def frozen(tmp_path):
    rows=[{"order":i,"block":i//4,"arm":arm,"seed":30+i//2} for i,arm in enumerate("ABBABAAB")]
    p=tmp_path/"schedule.json";p.write_text(json.dumps({"schema":1,"batch":"batch","attempts":rows}))
    return p,rows,{"SSBOT_FORUM_CHAIN_BATCH":"batch","SSBOT_FORUM_CHAIN_SCHEDULE":str(p),
                   "SSBOT_FORUM_CHAIN_BLOCK":"0","SSBOT_FORUM_CHAIN_ORDER":"0"}


def test_explicit_labels_are_metadata_but_frozen_sequence_is_bound(tmp_path):
    path,rows,env=frozen(tmp_path)
    conditions=execution_conditions(options(tmp_path),env)
    other={**env,"SSBOT_FORUM_CHAIN_BLOCK":"1","SSBOT_FORUM_CHAIN_ORDER":"4"}
    assert execution_conditions(options(tmp_path),other)==conditions
    assert attempt_labels(2,other)=={"block":1,"order":6}
    assert attempt_labels(0,{})=={"block":None,"order":None}
    changed=json.loads(path.read_text());changed["attempts"][1]["seed"]+=1
    path.write_text(json.dumps(changed))
    assert execution_conditions(options(tmp_path),env)!=conditions


@pytest.mark.parametrize("env",[{"SSBOT_FORUM_CHAIN_BLOCK":"0"},
 {"SSBOT_FORUM_CHAIN_BLOCK":"0","SSBOT_FORUM_CHAIN_ORDER":"-1"},
 {"SSBOT_FORUM_CHAIN_BLOCK":"x","SSBOT_FORUM_CHAIN_ORDER":"0"}])
def test_bad_labels_do_not_become_guessed_order(env):
    with pytest.raises(LearningStop):attempt_labels(0,env)


def test_frozen_schedule_rejects_wrong_next_slot_before_consuming_or_replacing(tmp_path):
    path,rows,env=frozen(tmp_path);b=LearningBudget(tmp_path/"budget.json",batch="batch",revision="r",worker="w")
    b.bind_execution(execution_conditions(options(tmp_path),env))
    b.begin_attempt(episode=0,policy_episode=1,**rows[0]);before=b.path.read_bytes()
    with pytest.raises(LearningStop,match="already reserved"):
        b.begin_attempt(episode=0,**rows[0])
    for bad in ({**rows[1],"arm":"A"},{**rows[1],"seed":999},{**rows[1],"order":2},{**rows[1],"block":1}):
        with pytest.raises(LearningStop,match="frozen crossover"):
            b.begin_attempt(episode=1,**bad)
        assert b.path.read_bytes()==before
    b.begin_attempt(episode=1,policy_episode=2,**rows[1])
    assert len(b.state["attempts"])==2 and b.state["attempts"][1]["order"]==1


def test_bad_schedule_is_refused_not_partially_used(tmp_path):
    path,rows,env=frozen(tmp_path)
    data=json.loads(path.read_text());data["attempts"][2]["order"]=1;path.write_text(json.dumps(data))
    with pytest.raises(LearningStop,match="schedule invalid"):crossover_schedule(env)


def context():
    return {"k":3,"instance":0,"seed":31,"arm":"B","batch":"batch","revision":"r","code_rev":"code",
      "reservation_id":"w:3","policy_episode_expected":4,"execution_sha256":"e","block":0,"order":3}


def rec():
    return AttemptRecord(unit="Forum_W_w7",stage="TRAIN",profile="TRAIN",build="test",code_rev="code",
      config_fp="fp",start_kind="savestate",mode="eval",seed=31,f_reset=400,f_wake=420,b2_context=context())


def test_actual_reset_binds_worker_k_and_policy_episode_before_fight():
    events=[];c=SimpleNamespace(b2=True,episode=4,arm="B",budget=SimpleNamespace(batch="batch",revision="r"),
      _note=lambda event,**v:events.append((event,v)),flush=lambda:events.append(("flush",{})))
    p=SimpleNamespace(chain_native=c);r=rec();_bind_b2_episode(p,r,425)
    event,v=events[0]
    assert event=="b2_episode_start" and v["k"]==3 and v["policy_episode"]==4
    assert v["f_reset"]==400 and v["frame"]==425 and v["block"]==0 and v["order"]==3
    assert events[-1][0]=="flush" and r.b2_context==v


def test_mismatched_policy_counter_does_not_claim_binding():
    c=SimpleNamespace(b2=True,episode=5,arm="B",budget=SimpleNamespace(batch="batch",revision="r"),
      _note=lambda *a,**v:pytest.fail("misbound"))
    with pytest.raises(LearningStop,match="binding mismatch"):_bind_b2_episode(SimpleNamespace(chain_native=c),rec(),425)


def test_non_b2_episode_has_no_new_runtime_requirement():
    r=rec();r.b2_context=None;_bind_b2_episode(SimpleNamespace(),r,425)


def test_worker_retains_labels_and_context_even_before_policy_replay(tmp_path,monkeypatch):
    rig=Rig(tmp_path,monkeypatch)
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_BLOCK","2");monkeypatch.setenv("SSBOT_FORUM_CHAIN_ORDER","6")
    assert rig.run(episodes=1)==0
    record=json.loads((tmp_path/"attempts_i0.jsonl").read_text().splitlines()[0])
    assert record["b2_reservation"]["block"]==2 and record["b2_reservation"]["order"]==6
    assert record["b2_context"]["k"]==0 and record["b2_context"]["policy_episode_expected"]==1
    assert record["b2_context"]["batch"]=="test-batch"


def test_stopped_episode_retains_actual_endpoint_before_release(monkeypatch):
    from ssbot.train import episode as E
    calls=[]
    link=SimpleNamespace(frame=425,state={"f":425})
    def fail(*a):raise LearningStop("B2 stopped: new chain-related fight injury")
    def release(*a,**kw):calls.append("release");link.frame=500
    link.act=release;link.rpc=lambda *a,**kw:calls.append("rpc")
    monkeypatch.setattr(E,"_run",fail);monkeypatch.setattr(E,"_summarise",lambda *a:None)
    r=rec();E.run_episode(link,None,None,SimpleNamespace(),None,r)
    assert r.outcome==E.HARNESS_FAIL and r.reason=="LearningStop: B2 stopped: new chain-related fight injury"
    # Sol seq354 (#407): the B2 bout's safe stop (input.release, time.scale) comes first, after the endpoint was kept
    assert r.f_end==425 and calls==["rpc","rpc","release","rpc"]
    assert r.b2_context["failure_frame"]=={"status":"observed","source":"link.frame before release","frame":425}
    assert r.b2_context["safe_stop"]["where"]=="episode_exception" and r.b2_context["safe_stop"]["frame"]==425


def test_unavailable_stop_frame_keeps_primary_failure_and_unknown(monkeypatch):
    from ssbot.train import episode as E
    class Link:
        state={}
        @property
        def frame(self):raise OSError("observer frame unavailable")
        def act(self,*a,**kw):pytest.fail("frame missing, no guessed action")
    def fail(*a):raise LearningStop("original failure")
    monkeypatch.setattr(E,"_run",fail);monkeypatch.setattr(E,"_summarise",lambda *a:None)
    r=rec();E.run_episode(Link(),None,None,SimpleNamespace(),None,r)
    assert r.outcome==E.HARNESS_FAIL and r.reason=="LearningStop: original failure" and r.f_end is None
    assert r.b2_context["failure_frame"]["status"]=="unknown"
