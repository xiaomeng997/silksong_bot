"""Explicit runtime B2/worker provenance; no game, env parser or model rollout."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from ssbot.train.forum_measure_manifest import configuration_manifest,_CHAIN_ROLES


def package(tmp_path,extra=()):
    root=tmp_path/"ssbot";(root/"combat").mkdir(parents=True)
    keys=[*_CHAIN_ROLES,*extra]
    source="\n".join(f'def read{i}(): return os.environ.get({key!r})' for i,key in enumerate(keys))
    source+='\ndef labels(env,k): return env.get("SSBOT_FORUM_CHAIN_"+k)\n'
    (root/"combat"/"example.py").write_text(source)
    return root


def env(**overrides):
    e={"SSBOT_FORUM_CHAIN_B2":"1","SSBOT_FORUM_CHAIN_NATIVE":"1","SSBOT_FORUM_CHAIN_ARM":"B",
       "SSBOT_FORUM_CHAIN_BATCH":"sample","SSBOT_FORUM_CHAIN_BUDGET":"C:/sample/budget.json",
       "SSBOT_FORUM_CHAIN_PROBE":"sample-probe","SSBOT_FORUM_CHAIN_BLOCK":"0","SSBOT_FORUM_CHAIN_ORDER":"0",
       "SSBOT_FORUM_CHAIN_SCHEDULE":"C:/sample/schedule.json"}
    e.update(overrides);return e


def policy(e):
    attempt={"worker":"i0","policy_episode":2,"block":0,"order":2}
    budget=SimpleNamespace(batch="sample",path=Path("C:/sample/budget.json"),worker="i0",
        state={"attempts":[attempt],"execution":{"conditions":{"crossover":{"sha256":"captured-file-sha",
            "schedule":{"batch":"sample","attempts":[{"order":0,"arm":"B"}]}}}}})
    chain=SimpleNamespace(b2=True,runner_factory=lambda:None,arm="B",profile=SimpleNamespace(short_frames=12,fast_hook=False,fixed_hook=False),
        probe_ref="sample-probe",budget=budget,episode=2,_environment=tuple(sorted(e.items())))
    return SimpleNamespace(chain_native=chain)


def manifest(root,p,e,context=None):
    return configuration_manifest(root,p,modules={"ssbot.combat.example":SimpleNamespace()},environ=e,runtime_context=context)


def test_chain_control_and_accounting_come_from_runtime_objects_not_env_defaults(tmp_path):
    root=package(tmp_path);e=env();p=policy(e);m=manifest(root,p,e)
    assert m["configuration_complete"] and not m["unresolved"]
    s=m["switches"]
    assert "SSBOT_FORUM_CHAIN_" not in s
    assert s["SSBOT_FORUM_CHAIN_ARM"]["role"]=="control"
    assert s["SSBOT_FORUM_CHAIN_ORDER"]["role"]=="accounting"
    assert s["SSBOT_FORUM_CHAIN_ORDER"]["effective"]=={"policy.chain_native.budget.attempt.order":2}
    assert s["SSBOT_FORUM_CHAIN_SHORT_FRAMES"]["raw"] is None
    assert s["SSBOT_FORUM_CHAIN_SHORT_FRAMES"]["effective"]=={"policy.chain_native.profile.short_frames":12}
    assert s["SSBOT_FORUM_CHAIN_SCHEDULE"]["effective"]["policy.chain_native.budget.execution.crossover"]["bound"]["sha256"]=="captured-file-sha"


def test_accounting_labels_stay_visible_without_changing_behavior_digest(tmp_path):
    root=package(tmp_path);e=env();p=policy(e);a=manifest(root,p,e)
    e2=env(SSBOT_FORUM_CHAIN_BATCH="another",SSBOT_FORUM_CHAIN_ORDER="3",SSBOT_FORUM_CHAIN_BUDGET="C:/another/budget.json")
    q=policy(e2);q.chain_native.budget.batch="another";q.chain_native.budget.path=Path("C:/another/budget.json")
    q.chain_native.budget.state["attempts"][0]["order"]=5
    b=manifest(root,q,e2)
    assert a["behavior_sha256"]==b["behavior_sha256"]
    assert a["switches"]["SSBOT_FORUM_CHAIN_BATCH"]!=b["switches"]["SSBOT_FORUM_CHAIN_BATCH"]
    q.chain_native.profile.short_frames=13
    assert manifest(root,q,e2)["behavior_sha256"]!=b["behavior_sha256"]


def test_missing_b2_profile_or_reserved_labels_is_unresolved_not_invented(tmp_path):
    root=package(tmp_path);e=env();p=policy(e)
    p.chain_native.profile=None;p.chain_native.budget.state["attempts"]=[]
    m=manifest(root,p,e)
    assert not m["configuration_complete"]
    assert {"SSBOT_FORUM_CHAIN_SHORT_FRAMES","SSBOT_FORUM_CHAIN_BLOCK","SSBOT_FORUM_CHAIN_ORDER"}<=set(m["unresolved"])


def test_real_env_key_that_looks_like_prefix_and_unknown_chain_key_are_not_ignored(tmp_path):
    root=package(tmp_path,extra=["SSBOT_FORUM_CHAIN_FUTURE"]);e=env(SSBOT_FORUM_CHAIN_="unexpected",SSBOT_FORUM_CHAIN_FUTURE="1")
    m=manifest(root,policy(e),e)
    assert not m["configuration_complete"]
    assert "SSBOT_FORUM_CHAIN_" in m["unknown_environment_switches"]
    assert "SSBOT_FORUM_CHAIN_FUTURE" in m["unresolved"]


def test_environment_change_since_construction_is_retained_as_conflict(tmp_path):
    root=package(tmp_path);e=env();p=policy(e)
    changed={**e,"SSBOT_FORUM_CHAIN_ARM":"A"}
    m=manifest(root,p,changed)
    assert not m["configuration_complete"]
    assert "SSBOT_FORUM_CHAIN_ARM: environment changed after construction" in m["unresolved"]
    assert m["switches"]["SSBOT_FORUM_CHAIN_ARM"]["effective"]=={"policy.chain_native.arm":"B"}


def test_worker_uses_executed_result_and_measured_process_without_reboosting(tmp_path):
    root=package(tmp_path);e=env(SSBOT_WORKER_BOOST="1",SSBOT_WORKER_CPUS="0-15")
    ctx={"worker":{"requested_environment":{k:e[k] for k in ["SSBOT_WORKER_BOOST","SSBOT_WORKER_CPUS"]},
                   "boost_result":"High, cpus 0-15, throttling off",
                   "runtime_before":{"cpu_affinity":list(range(16)),"priority":128,"numba_threads":4,"pid":12345}}}
    m=manifest(root,policy(e),e,ctx)
    assert m["configuration_complete"]
    for key in ["SSBOT_WORKER_BOOST","SSBOT_WORKER_CPUS"]:
        s=m["switches"][key];assert s["role"]=="execution"
        actual=s["effective"]["worker.executed_boost"]
        assert actual["requested_raw"]==e[key] and actual["observed"]["cpu_affinity"]==list(range(16))
        assert "pid" not in actual["observed"]
    ctx["worker"]["runtime_before"]["pid"]=55555
    assert manifest(root,policy(e),e,ctx)["behavior_sha256"]==m["behavior_sha256"]
    ctx["worker"]["runtime_before"]["cpu_affinity"]=[0,1]
    assert manifest(root,policy(e),e,ctx)["behavior_sha256"]!=m["behavior_sha256"]


def test_worker_missing_observation_and_environment_changes_do_not_certify(tmp_path):
    root=package(tmp_path);e=env(SSBOT_WORKER_BOOST="1",SSBOT_WORKER_CPUS="0-15");p=policy(e)
    m=manifest(root,p,e)
    assert {"SSBOT_WORKER_BOOST","SSBOT_WORKER_CPUS"}<=set(m["unresolved"])
    ctx={"worker":{"requested_environment":{"SSBOT_WORKER_BOOST":"0","SSBOT_WORKER_CPUS":"0-15"},
        "boost_result":"boost off","runtime_before":{"cpu_affinity":[16],"priority":64}}}
    m=manifest(root,p,e,ctx)
    assert "SSBOT_WORKER_BOOST: environment changed after worker boost" in m["unresolved"]


def test_disabled_chain_is_runtime_disabled_but_missing_policy_is_not_guessed(tmp_path):
    root=package(tmp_path);e={}
    m=manifest(root,SimpleNamespace(chain_native=None),e)
    assert m["configuration_complete"]
    assert m["switches"]["SSBOT_FORUM_CHAIN_B2"]["effective"]=={"policy.chain_native.b2":False}
    missing=manifest(root,SimpleNamespace(),e)
    assert not missing["configuration_complete"]
    assert "SSBOT_FORUM_CHAIN_B2" in missing["unresolved"]
