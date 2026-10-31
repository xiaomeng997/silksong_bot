"""Worker audit primary/secondary failures and actual boost context; no game."""
from copy import deepcopy
from types import SimpleNamespace
import json
import os
import pytest
from ssbot.tools import combat_run as C
from ssbot.combat.knife_chain_budget import LearningStop
from tests.test_b2_worker_batch import Rig

STOP={"frame":2667,"episode":1,"worker":"test","mode":"batch_end","reasons":["B fight cumulative 2 HP"]}
REASON="B2 stopped: B fight cumulative 2 HP"


def test_chain_stop_and_locked_budget_are_primary_not_harness_wrapper():
    original=deepcopy(STOP)
    got=C._b2_stop_details(REASON,STOP,REASON,outcome="HARNESS_FAIL",episode_reason="LearningStop: "+REASON)
    assert got["reason"]==REASON and got["origin"]=="chain.learning_stop" and got["budget_stop"]==STOP
    assert got["secondary_errors"]==[] and STOP==original
    got["budget_stop"]["reasons"].append("untrusted mutation")
    assert STOP==original
    fallback=C._b2_stop_details(None,STOP,REASON,outcome="HARNESS_FAIL",episode_reason="LearningStop: "+REASON)
    assert fallback["reason"]==REASON and fallback["origin"]=="budget.stop"


def test_integrity_failure_remains_secondary_to_original_stop():
    got=C._b2_stop_details(REASON,STOP,"B2 budget missing/corrupt",outcome="HARNESS_FAIL",episode_reason="wrapper")
    assert got["reason"]==REASON and got["secondary_errors"]==[
        {"origin":"budget.check","reason":"B2 budget missing/corrupt"},
        {"origin":"episode.exception","reason":"wrapper"}]
    unknown=C._b2_stop_details(None,None,None,outcome="HARNESS_FAIL",episode_reason="unknown reset failure")
    assert unknown["origin"]=="harness" and "unknown reset failure" in unknown["reason"]
    assert C._b2_stop_details(None,None,None,outcome="CLEAR",episode_reason=None) is None


def test_measurement_secondary_retains_unknown_window_without_filling_zero():
    window={"complete":False,"T":None,"hp_loss":None,"errors":["unobserved HP/time interval cannot be assumed empty"]}
    data={"measurement":{"trace_complete":True,"configuration_complete":False,"unresolved":["CHAIN_NATIVE"],"window":window}}
    got=C._measurement_incomplete_detail(data)
    assert got["window"]==window and got["window"]["T"] is None and got["window"]["hp_loss"] is None
    assert not got["configuration_complete"] and got["unresolved"]==["CHAIN_NATIVE"]


def measured_rig(tmp_path,monkeypatch,*,injury=True,manifest_error=False):
    rig=Rig(tmp_path,monkeypatch,fault="injury" if injury else None)
    import ssbot.ipc.oracle_link as ipc
    import ssbot.train.measurement as M
    import ssbot.train.forum_measure_manifest as F
    import ssbot.train.episode as E
    Base=ipc.OracleLink
    class Link(Base):
        hello={"scope":"fake worker transaction"}
        def subscribe_state(self,*a):pass
    monkeypatch.setattr(ipc,"OracleLink",Link)
    class Trace:
        def __init__(self,**kw):
            self.protocol_version=kw.get("protocol_version",2)
            self.window=SimpleNamespace(snapshot=lambda:{"complete":False,"watchdog_f":None,"T":None,"hp_loss":None,
                "errors":["unobserved HP/time interval cannot be assumed empty"]})
        def observe_state(self,*a):pass
        def start_episode(self,*a):pass
        def write(self,path):
            path.write_text("fake trace artifact for control-flow test")
            return {"complete":True,"scope":"fake trace writer"}
    monkeypatch.setattr(M,"MeasurementTrace",Trace)
    monkeypatch.setattr(M,"warm_query_kernels",lambda:{})
    monkeypatch.setattr(M,"prepare_lazy_configuration",lambda *a:None)
    monkeypatch.setattr(F,"code_manifest",lambda *a:{"scope":"fake source manifest"})
    monkeypatch.setattr(F,"runtime_manifest",lambda:{"cpu_affinity":[16,17],"priority":64,"numba_threads":1})
    contexts=[]
    def manifest(*a,runtime_context=None,**kw):
        contexts.append(deepcopy(runtime_context))
        if manifest_error:raise RuntimeError("manifest serialization failed")
        return {"configuration_complete":False,"unresolved":[{"key":"CHAIN_NATIVE","reason":"test missing binding"}],"behavior_sha256":"fake"}
    monkeypatch.setattr(F,"configuration_manifest",manifest)
    old=E.run_episode
    def run_episode(link,enc,tap,policy,cfg,record):
        old(link,enc,tap,policy,cfg,record)
        if injury:policy.chain_native.learning_stop=REASON
    monkeypatch.setattr(E,"run_episode",run_episode)
    actual={"cpu_affinity":[16,17],"priority":64,"power_throttling":{"query_error":"not observable","state_mask":None}}
    monkeypatch.setattr(C,"_worker_runtime_snapshot",lambda:deepcopy(actual))
    return rig,contexts


def measure_options():
    return dict(episodes=1,measure=True,measure_diagnostics=False,measurement_protocol=2,measure_max_records=100,
      measure_timing_only=False,engineering_probe=True)


def test_two_hp_primary_survives_measurement_incomplete_and_cleanup(tmp_path,monkeypatch):
    rig,contexts=measured_rig(tmp_path,monkeypatch)
    with pytest.raises(LearningStop,match="B fight cumulative 2 HP") as caught:rig.run(**measure_options())
    data=json.loads((tmp_path/"attempts_i0.jsonl").read_text().splitlines()[0])
    assert data["b2_learning_stop"]==REASON and data["b2_learning_stop_origin"]=="chain.learning_stop"
    worker_input=contexts[0]["worker"]["b2_input_path"]
    assert worker_input["receipt"]==str(tmp_path/"b2_input_path_i0.json")
    assert worker_input["verified"]=={"latency_frames":0,"min_press_frames":2,"min_release_frames":2,"pending":0}
    assert worker_input["peer"]==["127.0.0.1",47017]
    assert data["b2_budget_stop"]["reasons"]==["B fight cumulative 2 HP"]
    assert data["measurement"]["complete"] is False and data["measurement"]["configuration_complete"] is False
    assert data["measurement"]["window"]["T"] is None
    assert any(s["origin"]=="measurement" and s["unresolved"] for s in data["secondary_errors"])
    assert any("secondary" in n for n in caught.value.__notes__)
    cleanup=rig.receipts()[0]
    assert cleanup["primary_error"]=="LearningStop: "+REASON
    assert cleanup["primary_error_origin"]=="chain.learning_stop" and cleanup["complete"]
    assert any(s["origin"]=="measurement" for s in cleanup["secondary_errors"])
    assert rig.events.count("ready")==1 and rig.links[0].closed
    assert rig.budget.state["b_fight_hp"]==2 and len(rig.budget.state["attempts"])==1
    halt=json.loads((tmp_path/"budget.json.halt").read_text())
    assert halt["reason"]==REASON and halt["primary_error_origin"]=="chain.learning_stop"
    assert halt["secondary_errors"]==[{"origin":"measurement","reason":"measurement incomplete; stop before another episode"}]


def test_manifest_exception_is_secondary_after_locked_stop(tmp_path,monkeypatch):
    rig,contexts=measured_rig(tmp_path,monkeypatch,manifest_error=True)
    with pytest.raises(LearningStop,match="B fight cumulative 2 HP") as caught:rig.run(**measure_options())
    assert isinstance(caught.value.__cause__,RuntimeError)
    cleanup=rig.receipts()[0]
    assert cleanup["primary_error"]=="LearningStop: "+REASON
    assert any(s["origin"]=="worker.exception" and "manifest serialization failed" in s["reason"] for s in cleanup["secondary_errors"])
    assert rig.links[0].closed and rig.budget.state["b_fight_hp"]==2
    assert (tmp_path/"budget.json.halt").exists()


def test_boost_inputs_are_captured_once_before_call_and_passed_to_manifest(tmp_path,monkeypatch):
    rig,contexts=measured_rig(tmp_path,monkeypatch,injury=False)
    monkeypatch.delenv("SSBOT_WORKER_BOOST",raising=False);monkeypatch.setenv("SSBOT_WORKER_CPUS","0-15")
    calls=[]
    def boost():
        calls.append(1);monkeypatch.setenv("SSBOT_WORKER_BOOST","later-value");monkeypatch.setenv("SSBOT_WORKER_CPUS","16-31")
        return "actual result, throttling unchanged"
    monkeypatch.setattr(C,"boost_worker",boost)
    with pytest.raises(RuntimeError,match="measurement incomplete"):rig.run(**measure_options())
    assert len(calls)==1 and len(contexts)==1
    worker=contexts[0]["worker"]
    assert worker["requested_environment"]=={"SSBOT_WORKER_BOOST":None,"SSBOT_WORKER_CPUS":"0-15"}
    assert worker["boost_result"]=="actual result, throttling unchanged"
    assert worker["runtime_before"]["cpu_affinity"]==[16,17] and worker["runtime_before"]["priority"]==64
    assert worker["runtime_before"]["power_throttling"]["query_error"]=="not observable"
    assert worker["runtime_before"]["power_throttling"]["state_mask"] is None
    assert contexts[0]["attempt"]["k"]==0


def test_cleanup_failure_keeps_original_stop_and_secondary_resource_error(tmp_path,monkeypatch):
    from tests.test_b2_worker_batch import options,env
    env(monkeypatch,tmp_path)
    class Broken:
        def close(self):raise OSError("recorder finalization failed")
    result=C._close_worker(options(tmp_path),link=None,recorder=Broken(),out=None,diagnostics=None,policy=None,
      stage="episodes",primary_error="LearningStop: "+REASON,primary_error_origin="budget.stop",
      secondary_errors=[{"origin":"measurement","reason":"still incomplete"}])
    assert result["primary_error"]=="LearningStop: "+REASON and result["complete"] is False
    assert any(x["origin"]=="cleanup.recorder" for x in result["secondary_errors"])
    assert (tmp_path/"budget.json.halt").exists()


def test_actual_worker_runtime_query_is_read_only_and_does_not_guess_power_state():
    got=C._worker_runtime_snapshot()
    assert got["pid"]==os.getpid() and isinstance(got["cpu_affinity"],list) and isinstance(got["priority"],int)
    power=got["power_throttling"]
    assert power["provider"]=="GetProcessInformation"
    if power.get("query_error") is not None:assert "state_mask" not in power
    elif power.get("status")!="not_windows":assert type(power["state_mask"]) is int and type(power["control_mask"]) is int
