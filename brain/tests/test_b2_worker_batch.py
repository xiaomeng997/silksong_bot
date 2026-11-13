"""B2 collector transaction: fake IPC/Recorder, real persisted budget, no game."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from ssbot.combat.knife_chain_budget import (LearningBudget,LearningStop,execution_conditions,preflight_options)
from ssbot.tools import combat_run as C


def options(tmp_path,**overrides):
    d=dict(instance=0,run_dir=str(tmp_path),encounter="Forum_W_w7",mode="eval",policy="planner",view="oracle",
      episodes=4,hours=0.,rotate=1,seed=10,same_seeds=True,time_scale=1.,no_record=False,threads=1,
      real_quit=1.,inject_hits=0.,start_silk=None,start_hp=None,silk_reserve=False,forum_clash="main",
      key_cost=None,timebox=0.,measure=False)
    d.update(overrides);return SimpleNamespace(**d)


def env(monkeypatch,tmp_path,arm="B"):
    for k,v in dict(SSBOT_FORUM_CHAIN_B2="1",SSBOT_FORUM_CHAIN_NATIVE="1",SSBOT_FORUM_CHAIN_BATCH="test-batch",
      SSBOT_FORUM_CHAIN_ARM=arm,SSBOT_FORUM_CHAIN_BUDGET=str(tmp_path/"budget.json"),SSBOT_FORUM_CHAIN_PROBE="unit-ops").items():
        monkeypatch.setenv(k,v)


def test_both_arms_share_execution_identity_but_other_switch_changes_do_not():
    a=options(Path("run"));e={"SSBOT_FORUM_CHAIN_ARM":"A","SSBOT_FORUM_V2":"1"}
    assert execution_conditions(a,e)==execution_conditions(a,{**e,"SSBOT_FORUM_CHAIN_ARM":"B"})
    assert execution_conditions(a,e)!=execution_conditions(a,{**e,"SSBOT_FORUM_V2":"0"})
    assert execution_conditions(a,e)!=execution_conditions(options(Path("another"),timebox=12.),e)
    assert execution_conditions(a,e)==execution_conditions(options(Path("another"),seed=999,episodes=1),e)


def test_changed_conditions_preserve_original_batch(tmp_path):
    b=LearningBudget(tmp_path/"budget.json",batch="b",revision="r",worker="i0")
    b.bind_execution({"threads":4});before=b.path.read_bytes()
    with pytest.raises(LearningStop,match="NEW batch"):b.bind_execution({"threads":8})
    assert b.path.read_bytes()==before


def test_reservation_caps_total_eight_across_workers_and_keeps_all_slots(tmp_path):
    a=LearningBudget(tmp_path/"b.json",batch="b",revision="r",worker="i0")
    b=LearningBudget(tmp_path/"b.json",batch="b",revision="r",worker="i1")
    a.bind_execution({"profile":"first-smoke"});b.bind_execution({"profile":"first-smoke"})
    for i in range(8):
        owner=a if i%2==0 else b
        owner.begin_attempt(episode=i//2,arm="A" if i%2==0 else "B",seed=i//2)
    with pytest.raises(LearningStop,match="upper limit"):a.begin_attempt(episode=4,arm="A",seed=4)
    assert len(a.state["attempts"])==8
    assert a.state["stop"]["mode"]=="batch_end"


def test_four_per_arm_and_duplicate_do_not_become_replacement_games(tmp_path):
    b=LearningBudget(tmp_path/"b.json",batch="b",revision="r",worker="i0")
    b.bind_execution({"profile":"first-smoke"})
    b.begin_attempt(episode=0,arm="B",seed=0);before=b.path.read_bytes()
    with pytest.raises(LearningStop,match="already reserved"):b.begin_attempt(episode=0,arm="B",seed=0)
    assert b.path.read_bytes()==before
    for i in range(1,4):b.begin_attempt(episode=i,arm="B",seed=i)
    with pytest.raises(LearningStop,match="upper limit"):b.begin_attempt(episode=4,arm="B",seed=4)
    assert len(b.state["attempts"])==4


@pytest.mark.parametrize("change",[{"mode":"data"},{"time_scale":2.},{"inject_hits":1.},
    {"view":"degraded"},{"real_quit":0.},{"episodes":5},{"instances":"0,1","episodes":4}])
def test_invalid_smoke_options_rejected_before_parent_allocates_or_spawns(tmp_path,monkeypatch,change):
    env(monkeypatch,tmp_path)
    monkeypatch.setattr(C,"new_run_dir",lambda *a,**k:pytest.fail("allocated invalid run"))
    with pytest.raises(LearningStop):C.run(options(tmp_path,**change))


class Rig:
    def __init__(self,tmp_path,monkeypatch,fault=None,arm="B"):
        import ssbot.ipc.oracle_link as ipc
        import ssbot.record.recorder as recording
        import ssbot.train.episode as episode
        import ssbot.train.recovery as recovery
        self.root=tmp_path;self.events=[];self.links=[];self.fault=fault;self.attempts=0
        self.freeze_fault=None     # Sol seq354 (#407): "raise" or "unfrozen" makes the stopped bout's freeze fail
        env(monkeypatch,tmp_path,arm)
        rig=self
        class Link:
            def __init__(self,**kwargs):
                rig.events.append("ipc.open")
                if rig.fault=="connect":raise RuntimeError("connect failed")
                self.closed=False;self.frame=1000
                self.sock=SimpleNamespace(getpeername=lambda:("127.0.0.1",47017))
                self.state={"f":1000,"game":{"scene":"Menu_Title"},"hero":None}
                rig.links.append(self)
            def rpc(self,method,**kwargs):
                if method in ("input.release","time.scale"):
                    # the stopped B2 bout's freeze (train.episode.b2_safe_stop): component evidence only, no game here
                    rig.events.append(method+(" "+repr(kwargs.get("scale")) if method=="time.scale" else ""))
                    if method=="time.scale" and rig.freeze_fault=="raise":raise TimeoutError("time.scale timed out")
                    if method=="time.scale":return {"time_scale":1. if rig.freeze_fault=="unfrozen" else kwargs.get("scale")}
                    return {}
                assert method=="input.stats" and kwargs=={"timeout_s":10.}
                rig.events.append("input.stats")
                if rig.fault=="input_rpc":raise RuntimeError("input.stats failed")
                result={"latency":{"delay_frames":0,"jitter_frames":0,"dist":None},
                        "hold":{"min_press_frames":2,"min_release_frames":2},"pending":0}
                if rig.fault=="input_pending":result["pending"]=1
                return result
            def wait_state(self,*a,**k):return self.state
            def close(self):rig.events.append("ipc.close");self.closed=True
        class Recorder:
            def __init__(self,*a,**k):self.path=tmp_path/"recording";rig.events.append("recorder.new")
            def start(self):rig.events.append("recorder.start");return self
            def close(self):
                rig.events.append("recorder.close")
                if rig.fault=="recorder_close":raise OSError("index save failed")
        class Policy:
            def __init__(self):
                self.episode=0;self.chain_native=None
                if rig.fault=="policy":raise RuntimeError("policy failed")
            def attach(self,link):self.link=link
            def prepare_learning_batch(self,a):
                rig.events.append("batch.prepare")
                b=LearningBudget(tmp_path/"budget.json",batch="test-batch",revision="frozen-unit",
                    worker=str(Path(a.run_dir)/"decisions.chain.jsonl"))
                b.bind_execution(execution_conditions(a));self.chain_native=SimpleNamespace(b2=True,budget=b,flush=lambda:rig.events.append("chain.flush"))
                rig.budget=b;return b
            def warmup(self):
                rig.events.append("warmup")
                self.b2_warmup_report={"scope":"fake model warm-up for worker transaction test","compiled_signatures":{}}
                if rig.fault=="warmup":raise RuntimeError("warmup failed")
                return 0.
            def flush_log(self):rig.events.append("policy.flush")
            def flush_keys(self):rig.events.append("keys.flush")
        monkeypatch.setattr(ipc,"OracleLink",Link)
        monkeypatch.setattr(recording,"Recorder",Recorder)
        monkeypatch.setattr(episode,"make_tap",lambda *a:SimpleNamespace())
        monkeypatch.setattr(C,"make_policy",lambda *a,**k:Policy())
        monkeypatch.setattr(C,"boost_worker",lambda:"fake boost")
        monkeypatch.setattr(C,"git_rev",lambda:"frozen-unit")
        monkeypatch.setattr(recovery,"is_paused",lambda s:False)
        monkeypatch.setattr(C,"_in_game_without_control",lambda s:False)
        monkeypatch.setattr(C,"back_into_slot",lambda *a:rig.events.append("back_into_slot"))
        monkeypatch.setattr(C,"set_time_scale",lambda *a:rig.events.append("time_scale"))
        monkeypatch.setattr(C,"ready_for_episode",lambda *a:(rig.events.append("ready") or None,1.))
        monkeypatch.setattr(C,"stop_requested",lambda *a:False)
        def run_episode(link,enc,tap,pol,cfg,rec):
            rig.attempts+=1;rig.events.append("episode");pol.episode+=1
            assert len(pol.chain_native.budget.state["attempts"])==rig.attempts
            rec.outcome="CLEAR";rec.ingame_s=1.
            if rig.fault=="injury":
                try:pol.chain_native.budget.observe(episode=pol.episode,frame=1001,arm="B",hp_loss=2)
                except LearningStop as exc:rec.outcome="HARNESS_FAIL";rec.reason=str(exc)
            if rig.fault=="episode":raise RuntimeError("episode failed")
        monkeypatch.setattr(episode,"run_episode",run_episode)
        def after_episode(link,enc,instance,d):
            rig.events.append("after_episode")
            # The attempt and its reservation must be durable BEFORE cleanup.
            path=Path(rig.args.run_dir)/"attempts_i0.jsonl"
            assert json.loads(path.read_text().splitlines()[-1])["b2_reservation"]["seed"]==d["seed"]
        monkeypatch.setattr(C,"after_episode",after_episode)
    def run(self,**overrides):
        self.args=options(self.root,**overrides)
        return C.worker(self.args)
    def receipts(self):
        return [json.loads(p.read_text()) for p in self.root.glob("worker_cleanup_i*.json")]


@pytest.mark.parametrize("fault",["connect","policy","warmup"])
def test_bootstrap_failure_preserves_halt_and_closes_every_created_resource(tmp_path,monkeypatch,fault):
    rig=Rig(tmp_path,monkeypatch,fault=fault)
    with pytest.raises(RuntimeError,match="failed"):rig.run()
    assert rig.attempts==0
    assert (tmp_path/"budget.json.halt").exists()
    receipts=rig.receipts();assert len(receipts)==1 and receipts[0]["complete"]
    assert receipts[0]["resources"]["attempts"]=="pass"
    assert all(p.closed for p in rig.links)
    assert "ready" not in rig.events


def test_two_hp_stop_writes_attempt_then_cleanup_without_another_ready(tmp_path,monkeypatch):
    rig=Rig(tmp_path,monkeypatch,fault="injury")
    assert rig.run()==0
    assert rig.attempts==1 and rig.events.count("ready")==1
    # Sol seq354 (#407): the stopped bout's game is frozen first and stays so: no after_episode (pause resume, menu return)
    assert rig.events.index("episode")<rig.events.index("time.scale 0.0001")<rig.events.index("ipc.close")
    assert "after_episode" not in rig.events
    assert rig.budget.state["b_fight_hp"]==2 and len(rig.budget.state["attempts"])==1
    assert len((tmp_path/"attempts_i0.jsonl").read_text().splitlines())==1
    assert rig.receipts()[0]["complete"]


def test_recorder_failure_still_closes_ipc_and_halts_batch(tmp_path,monkeypatch):
    rig=Rig(tmp_path,monkeypatch,fault="recorder_close")
    with pytest.raises(RuntimeError,match="cleanup failed"):rig.run(episodes=1)
    assert rig.links[0].closed
    receipt=rig.receipts()[0]
    assert receipt["complete"] is False and receipt["resources"]["ipc"]=="pass"
    assert (tmp_path/"budget.json.halt").exists()


def test_successful_worker_reserves_before_ready_and_retains_config_identity(tmp_path,monkeypatch):
    rig=Rig(tmp_path,monkeypatch)
    assert rig.run(episodes=2)==0
    assert rig.attempts==2 and len(rig.budget.state["attempts"])==2
    assert all(a["execution_sha256"]==rig.budget.state["execution"]["sha256"] for a in rig.budget.state["attempts"])
    assert rig.receipts()[0]["resources"]["ipc"]=="pass"
    assert rig.receipts()[0]["scope"].startswith("worker files/IPC only")


def test_primary_episode_exception_survives_and_owned_handles_close(tmp_path,monkeypatch):
    rig=Rig(tmp_path,monkeypatch,fault="episode")
    with pytest.raises(RuntimeError,match="episode failed"):rig.run(episodes=1)
    assert rig.links[0].closed and rig.events.count("recorder.close")==1
    assert "episode failed" in rig.receipts()[0]["primary_error"]


def test_cap_is_checked_before_recorder_ready_or_episode_reset(tmp_path,monkeypatch):
    rig=Rig(tmp_path,monkeypatch,arm="A")
    b=LearningBudget(tmp_path/"budget.json",batch="test-batch",revision="frozen-unit",worker="previous-worker")
    b.bind_execution(execution_conditions(options(tmp_path)))
    for i in range(4):b.begin_attempt(episode=i,arm="A",seed=i)
    with pytest.raises(LearningStop,match="upper limit"):rig.run(episodes=1)
    assert rig.attempts==0 and "ready" not in rig.events and "recorder.start" not in rig.events
    assert rig.links[0].closed and len(rig.budget.state["attempts"])==4


def test_real_policy_can_freeze_batch_at_title_without_missing_hp_stop(tmp_path,monkeypatch):
    from types import MethodType
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    from ssbot.train import forum_planner_policy as P
    env(monkeypatch,tmp_path)
    monkeypatch.setattr(P.kin,"hero2_on",lambda:True)
    p=SimpleNamespace(crest="Wanderer",clash="off",m2=None,air_show=None,wpress=None,chain_native=None,
      planner=None,episode=0,log_path=tmp_path/"decisions.jsonl",_fcfg=lambda c:SimpleNamespace(v2=True),
      link=SimpleNamespace(frame=1000,state={"f":1000,"hero":None,"game":{"scene":"Menu_Title"}}))
    p._reset_chain_native=MethodType(ForumPlannerPolicy._reset_chain_native,p)
    b=ForumPlannerPolicy.prepare_learning_batch(p,options(tmp_path))
    assert b.state["execution"] is not None and b.state["attempts"]==[]
    assert p.chain_native._budget_hp is None and b.state["stop"] is None


def test_cleanup_failure_does_not_replace_original_failure(tmp_path,monkeypatch):
    env(monkeypatch,tmp_path)
    events=[]
    class Failing:
        def close(self):events.append("recorder");raise OSError("bad index")
    link=SimpleNamespace(closed=False,close=lambda:events.append("ipc"))
    out=SimpleNamespace(close=lambda:events.append("attempts"))
    result=C._close_worker(options(tmp_path),link=link,recorder=Failing(),out=out,diagnostics=None,policy=None,
        stage="episodes",primary_error="RuntimeError: original failure")
    assert events==["recorder","attempts","ipc"] and result["complete"] is False
    assert result["primary_error"]=="RuntimeError: original failure"


@pytest.mark.parametrize("fault", ["input_rpc", "input_pending"])
def test_worker_input_preflight_failure_retains_raw_receipt_and_cleans_without_reset(tmp_path,monkeypatch,fault):
    rig=Rig(tmp_path,monkeypatch,fault=fault)
    with pytest.raises((RuntimeError,ValueError),match="input.stats"):
        rig.run(episodes=1)
    receipt=json.loads((tmp_path/"b2_input_path_i0.json").read_text())
    assert receipt["passed"] is False and receipt["instance"]==0
    assert receipt["peer"]==["127.0.0.1",47017] and receipt["error"]
    assert "batch.prepare" not in rig.events and "back_into_slot" not in rig.events
    assert rig.attempts==0 and rig.links[0].closed
    assert (tmp_path/"budget.json.halt").exists()
    assert rig.receipts()[0]["stage"]=="input_path_preflight"


REAL_AFTER_EPISODE=C.after_episode


def quit_rig(tmp_path,monkeypatch,where="title",main_menu=True,outcome="QUIT"):
    """Rig with the real after_episode and an episode that ends as a real quit, the link on `where`."""
    import ssbot.train.episode as episode
    import ssbot.train.recovery as recovery
    rig=Rig(tmp_path,monkeypatch)
    monkeypatch.setattr(C,"after_episode",REAL_AFTER_EPISODE)
    states={"title":{"game":{"gs":recovery.GS_MAIN_MENU,"menu":recovery.MENU_MAIN,"scene":"Menu_Title"}},
            "no_game":{"game":None},"quitting":{"game":{"gs":5,"menu":10,"scene":"Quit_To_Menu"}}}
    def run_episode(link,enc,tap,pol,cfg,rec):
        rig.attempts+=1;rig.events.append("episode");pol.episode+=1
        rec.outcome=outcome;rec.ingame_s=1.
        rec.policy={"real_quit":{"armed":True,"main_menu":main_menu,"steps":[[0.1,"done",""]]}}
        link.state={"f":2855,**states[where],"hero":None}
    monkeypatch.setattr(episode,"run_episode",run_episode)
    return rig


def after_start(rig):
    """back_into_slot calls after the worker's own one at its start."""
    return rig.events.count("back_into_slot")-1


def test_the_only_engineering_episode_really_quit_goes_straight_to_the_real_cleanup(tmp_path,monkeypatch,capsys):
    rig=quit_rig(tmp_path,monkeypatch)
    assert rig.run(episodes=1,engineering_probe=True)==0
    assert after_start(rig)==0
    assert "straight to the cleanup" in capsys.readouterr().out
    # the cleanup itself is untouched: every owned resource closed, after the attempt was written
    assert rig.events.index("episode")<rig.events.index("policy.flush")<rig.events.index("recorder.close")<rig.events.index("ipc.close")
    receipt=rig.receipts()[0];assert receipt["complete"] and receipt["resources"]["ipc"]=="pass" and receipt["resources"]["recorder"]=="pass"
    row=json.loads((tmp_path/"attempts_i0.jsonl").read_text().splitlines()[-1])
    assert row["outcome"]=="QUIT" and row["episode"]==0


def test_a_real_quit_with_a_next_episode_still_returns_to_the_slot(tmp_path,monkeypatch):
    rig=quit_rig(tmp_path,monkeypatch)
    assert rig.run(episodes=2,engineering_probe=True)==0
    assert rig.attempts==2 and after_start(rig)==2     # also after the last of many: its reset is not this change's
    assert rig.events.index("back_into_slot",1)<rig.events.index("ready",rig.events.index("ready")+1)
    assert rig.receipts()[0]["complete"]


@pytest.mark.parametrize("kw,why",[({"episodes":1},"a formal run")])
def test_a_formal_single_episode_keeps_the_return(tmp_path,monkeypatch,kw,why):
    rig=quit_rig(tmp_path,monkeypatch)
    assert rig.run(**kw)==0
    assert after_start(rig)==1,why


@pytest.mark.parametrize("where",["no_game","quitting"])
def test_a_quit_not_seen_on_the_title_keeps_the_return(tmp_path,monkeypatch,where):
    rig=quit_rig(tmp_path,monkeypatch,where=where)
    assert rig.run(episodes=1,engineering_probe=True)==0
    assert after_start(rig)==1


def test_an_unconfirmed_quit_or_a_harness_failure_keeps_after_episode(tmp_path,monkeypatch):
    calls=[]
    rig=quit_rig(tmp_path,monkeypatch,main_menu=False)
    monkeypatch.setattr(C,"after_harness_fail",lambda *a:calls.append("harness") or None)
    assert rig.run(episodes=1,engineering_probe=True)==0
    assert after_start(rig)==1          # the old rule: the quit's steps were seen, back into the slot
    assert not calls
    assert not C.only_episode_really_quit(rig.args,1,{"outcome":"HARNESS_FAIL","policy":{"real_quit":{"main_menu":True}}},rig.links[0])
    assert not C.only_episode_really_quit(rig.args,0,{"outcome":"QUIT","policy":{"real_quit":{"main_menu":True}}},rig.links[0])


def test_a_stop_in_the_only_episode_keeps_its_record_without_the_return(tmp_path,monkeypatch):
    rig=quit_rig(tmp_path,monkeypatch)
    import ssbot.train.episode as episode
    quit_episode=episode.run_episode
    def run_episode(link,enc,tap,pol,cfg,rec):
        quit_episode(link,enc,tap,pol,cfg,rec)
        with pytest.raises(LearningStop):pol.chain_native.budget.observe(episode=pol.episode,frame=1001,arm="B",hp_loss=2)
    monkeypatch.setattr(episode,"run_episode",run_episode)
    assert rig.run(episodes=1,engineering_probe=True)==0
    row=json.loads((tmp_path/"attempts_i0.jsonl").read_text().splitlines()[-1])
    assert row["b2_learning_stop"] and rig.budget.state["stop"] is not None
    assert after_start(rig)==0 and rig.receipts()[0]["complete"] and rig.links[0].closed


@pytest.mark.parametrize("arm", ["A","B"])
def test_both_arms_query_actual_worker_before_policy_and_action_preparation(tmp_path,monkeypatch,arm):
    rig=Rig(tmp_path,monkeypatch,arm=arm)
    assert rig.run(episodes=1)==0
    assert rig.events.index("ipc.open")<rig.events.index("input.stats")<rig.events.index("batch.prepare")
    assert rig.events.index("input.stats")<rig.events.index("back_into_slot")
    receipt=json.loads((tmp_path/"b2_input_path_i0.json").read_text())
    assert receipt["passed"] is True and receipt["verified"]["pending"]==0
    assert rig.events.count("input.stats")==1
