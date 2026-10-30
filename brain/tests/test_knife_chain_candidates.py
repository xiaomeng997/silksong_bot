"""Native row generation/real transport transactions, not a live-game certificate."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json

import numpy as np
import pytest

from ssbot.combat.knife_chain_candidates import NativeChainCandidates
from ssbot.combat.knife_chain_format import MASK_NAMES, table_digest
from ssbot.train import episode
from tests.test_knife_chain_eval import runner, table
from tests.test_knife_chain_native import wire_link, unpack


def state(f, **act):
    return {"f": f, "dt": 1/60, "hero": {"health": 5, "anim": {"clip": "Idle"}},
            "ents": [{"iid": 7, "type_key": "Song Heavy Sentry", "hp": 100, "pos": [25., 4.],
                      "fsms": [{"name": "Control", "state": "Slam Antic", "t": 0.}]}],
            "act": {"target": -1, "applied": -1, "mask": 0, **act}}


class Policy:
    action_flags = 0
    measurement_choice = None
    def __init__(self, audit, *, owner="plan", choose=True):
        self.chain_native, self.owner, self.choose = audit, owner, choose
    def act(self, s, tap):
        a = self.chain_native
        f = s["f"]
        a.begin(s)
        prefix = np.array([a._receipts.get(f + 1, 0)])
        a.planner_input(origin=f, prefix=prefix, hold=hold(), hero_state=np.zeros(3))
        a.prepare(s, ground=True, accepting=True, sim=SimpleNamespace(fo=f, f=f))
        rows = a.rows(T=6, origin=f, prefix=prefix, hold=hold(), hero_state=np.zeros(3))
        mask = 0
        index = -1
        if rows is not None:
            mask = int(rows[0][0, 0])
            a.register_candidate(4)
            if self.choose:
                index = 4
        a.planner_result(SimpleNamespace(idx=index, mask=mask, name="test"))
        a.final(self.owner, mask)
        return mask


def hold():
    z = np.zeros((1, 2), dtype=np.int64)
    return SimpleNamespace(latched=z, desired=z, pending=z, age=z)


def audit(tmp_path=None, factory=runner):
    return NativeChainCandidates(runner_factory=factory, probe_ref="offline:native-transaction-v1",
        journal=None if tmp_path is None else tmp_path / "chain.jsonl")


def seed(a):
    # Real ordinary ACTION, not a fabricated intended prefix.
    a.begin(state(99))
    a.final("plan", 0)
    a.before_send(frame=99, target=101, mask=0, flags=0, received_frame=99)
    from tests.test_knife_chain_native import wire_link
    wire_link().act(101, 0)
    a.sent()


def test_bound_v01_data_is_exact_accepted_reference():
    from ssbot.combat import knife_chain_slam as family
    from ssbot.combat.knife_chain_format import chains_from_json
    chains = chains_from_json(json.loads(Path(family.__file__).with_name("knife_chain_slam_v01.json").read_text("utf-8")))
    assert table_digest(chains) == "91b62e8b5cc221febcf255fb92f23afa096570ee827fa63ed2b6b4d16e31b603"
    r = family.make_runner(chains)
    assert r.binding["table_digest"] == table_digest(chains)
    assert len(r.chains["slam_jump"].links) == 24 and len(r.chains["slam_claw"].links) == 5
    assert len(family.LITERAL_NAMES) == 54
    assert len([x for x in family.P.catalog() if x["category"] == "C"]) == 5


def test_no_actual_prefix_receipt_no_row_and_no_zero_padding():
    a = audit()
    Policy(a).act(state(100), None)
    assert a.runner.run is None and a.counts["chain_proposal"] == 0
    assert a.events[-2]["event"] == "planner_selected"
    assert any("send receipt" in x.get("reason", "") for x in a.events)


@pytest.mark.parametrize("owner,choose,committed", [("plan", True, True), ("sup", True, False),
                                                   ("slam", True, False), ("plan", False, False)])
def test_commit_only_after_real_send_with_exact_final_owner(owner, choose, committed, tmp_path):
    a = audit(tmp_path); seed(a)
    before = deepcopy(a.runner.fired)
    link = wire_link(a)
    old_sendall = link.sock.sendall
    def checked_send(packet):
        assert a.runner.run is None and a.runner.fired == before
        assert a.dispatch.sent_for(102) is None
        old_sendall(packet)
    link.sock.sendall = checked_send
    episode._act(link, 100, Policy(a, owner=owner, choose=choose), state(100), None)
    assert bool(a.runner.run) == committed
    assert a.counts["chain_intent_committed"] == int(committed)
    assert unpack(link.packets[-1])[:3] == [102, MASK_NAMES["R"], 0]
    assert a.dispatch.sent_for(102).wire_mask is None
    lines = [json.loads(s) for s in (tmp_path / "chain.jsonl").read_text("utf-8").splitlines()]
    assert sum(x["event"] == "transport_sent" for x in lines) == 2


def test_send_failure_does_not_commit_or_add_receipt():
    a = audit(); seed(a)
    with pytest.raises(ConnectionError):
        episode._act(wire_link(a, fail=True), 100, Policy(a), state(100), None)
    assert a.runner.run is None and a._draft is None
    assert a.dispatch.sent_for(102) is None and a.counts["chain_intent_committed"] == 0


@pytest.mark.parametrize("desired,expected", [(MASK_NAMES["R"], "chain_application_observed"),
                                             (0, "chain_application_mismatch"),
                                             (None, "chain_application_unknown")])
def test_observed_application_does_not_fabricate_hero_action(desired, expected):
    a = audit(); seed(a)
    episode._act(wire_link(a), 100, Policy(a), state(100), None)
    a.observe(state(101))
    a.observe(state(102, target=102, applied=102, mask=0, hf={"desired": desired}))
    assert a.counts[expected] == 1
    assert a.dispatch.sent_for(102).wire_mask is None
    if desired != MASK_NAMES["R"]:
        assert a.runner.run is None
    else:
        assert a.runner.run is not None
        assert [e for e in a.events if e["event"] == expected][-1]["contact"] == "unchecked"


def test_unknown_or_coalesced_application_invalidates_next_run_not_queued_keys():
    a = audit(); seed(a)
    episode._act(wire_link(a), 100, Policy(a), state(100), None)
    for f in range(101, 106): a.observe(state(f))
    assert a.runner.run is None and a.counts["chain_application_unknown"] == 1
    assert a.dispatch.sent_for(102).desired_mask == MASK_NAMES["R"]


def test_episode_reset_clears_private_run_receipts_and_history():
    a = audit(); seed(a)
    episode._act(wire_link(a), 100, Policy(a), state(100), None)
    old_offer = a.dispatch.selection.offer
    a.reset(2, start_frame=10)
    assert a.runner.run is None and not a._receipts and not a._pending and not a._ticks
    assert a.dispatch.sent_for(102) is None
    a.begin(state(11))
    with pytest.raises(ValueError): a.dispatch.select(old_offer, probe_ref="old")


def test_pulse_projection_is_not_a_future_closed_loop_path():
    a = audit(); seed(a)
    Policy(a).act(state(100), None)
    assert a._draft.run.sent == [(102, MASK_NAMES["R"])]
    p = [e for e in a.events if e["event"] == "chain_proposal"][-1]
    assert p["projection"] == "pulse_release" and p["admission"] == "unchecked"
    assert a.runner.run is None


def test_hook_keys_are_unchecked_not_run_through_ordinary_hero_motion():
    def hook():
        t = table(); t["test"].links["start"].keys[0].mask = "CLAW"
        return runner(t)
    a = audit(factory=hook); seed(a)
    Policy(a).act(state(100), None)
    assert a.counts["chain_proposal"] == 0
    assert any("hook motion" in x.get("reason", "") for x in a.events)


def test_unknown_clock_is_not_replaced_by_wall_clock():
    a = audit(); seed(a)
    s = state(100); s.pop("dt")
    Policy(a).act(s, None)
    assert a._context is None and a.counts["chain_proposal"] == 0


def test_native_activation_needs_named_probe_and_journal(monkeypatch):
    from ssbot.combat import knife_chain_slam
    monkeypatch.setattr(knife_chain_slam, "load_runner", runner)
    with pytest.raises(ValueError, match="journal"):
        NativeChainCandidates.from_env(journal=None)
    monkeypatch.delenv("SSBOT_FORUM_CHAIN_PROBE", raising=False)
    with pytest.raises(ValueError, match="probe_ref"):
        NativeChainCandidates.from_env(journal="unused.jsonl")


@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize("v2_on", [False, True])
def test_real_planner_evaluates_native_row_and_never_keeps_a_static_continue(monkeypatch, allowed, v2_on):
    import math
    from ssbot.combat import forum_planner as fp, forum_v2 as v2, dslash, special_mode
    from ssbot.combat.planner import PlannerConfig
    from ssbot.combat.tactics.modes import GoalPrefs
    from ssbot.knowledge import kinematics as k
    from ssbot.map2.envelope import load_params
    from tests.test_forum_planner import _ctx, _world, _reed_forecaster
    from tests.test_forum_v2 import _support_with
    params = load_params(hero2=True)
    terrain = k.Terrain2D.from_boxes([(10., 0., 53., 3.)])
    start = k.initial_state(params, 27., 3. + params.foot)
    h = k.HoldState.idle(); prefix = np.array([0], np.int64)
    planner = fp.ForumPlanner(params, terrain, PlannerConfig(T=36, threads=1, variants="bounds", tail_k=0),
        fp.ForumConfig(v2=v2_on, deadline_ms=math.inf, esc_deadline_ms=math.inf), crest="Wanderer")
    monkeypatch.setattr(dslash, "DSLASH", False)
    monkeypatch.setattr(special_mode, "HITS_FIRST", False)
    a = audit(); seed(a)
    a.begin(state(100)); a.planner_input(origin=100, prefix=prefix, hold=h, hero_state=start)
    a.prepare(state(100), ground=True, accepting=True, sim=SimpleNamespace(fo=100, f=100))
    planner.chain_native = a
    # Keep one ordinary WAIT row: exercise real selection with a controlled
    # two-row input, without fabricating the full set's diversity/scoring tiers.
    for sets in (planner.fsets, planner.fsets_nc):
        for posture, (cs, core) in list(sets.items()):
            keep = np.zeros(len(cs.cmd), bool); keep[0] = True
            sets[posture] = (cs.subset(keep), core[keep])
    original_score = planner._score_forum
    def score(*args, **kwargs):
        sc = original_score(*args, **kwargs)
        # Controlled ranking incentive only; safety and row-key veto stay real.
        for i in a._rows: sc["J"][i] = 1e9
        return sc
    monkeypatch.setattr(planner, "_score_forum", score)
    forecast = _reed_forecaster(None, x=45.).forecast(.8)
    if v2_on: forecast = v2.V2Forecast(forecast, _support_with([]))
    ws = _world(27.); ws.stamp.frame = 100
    ctx = _ctx()
    if not allowed:
        from ssbot.combat.candidates import Prim
        ctx.allowed_mask[int(Prim.MOVE)] = False
    result = planner.tick(ws, start, h, prefix, forecast, GoalPrefs("ENGAGE", 27., {}), ctx)
    assert len(a._rows) == 1
    cr = next(iter(a._rows))
    ev = [e for e in a.events if e["event"] == "chain_row_evaluated"][-1]
    assert ev["allowed"] == allowed
    assert ev["enveloped"] == allowed
    if allowed:
        assert result.idx == cr and result.name == "CHAIN test.start" and result.mask == MASK_NAMES["R"]
        assert result.cmd.tolist() == [MASK_NAMES["R"]] + [0]*35
        assert planner.prev_cmd is None
    else:
        assert result.idx != cr
    # Ranking and even a returned result have not sent or advanced the Run.
    a.planner_result(result)
    assert a.runner.run is None and a.dispatch.sent_for(102) is None
    a.final("plan", result.mask)
    # Continue through the actual episode sender and ACTION framing after the
    # real planner chose/rejected the freshly generated native row.
    policy = SimpleNamespace(chain_native=a, act=lambda s,tap:result.mask, action_flags=0)
    link = wire_link(a)
    episode._act(link, 100, policy, state(100), None)
    assert bool(a.runner.run) == allowed
    assert unpack(link.packets[-1])[:3] == [102, int(result.mask), 0]


@pytest.mark.parametrize("mask,primitive", [("DASH", "DASH"), ("A", "ATTACK_SIDE"),
    ("D|A", "ATTACK_DOWN"), ("U|A", "ATTACK_UP"), ("J", "GLIDE"), ("R", "MOVE")])
def test_native_allowlist_checks_actual_key_kind(mask, primitive):
    from ssbot.combat.knife_chain_candidates import rows_allowed
    from ssbot.core.primitives import N_PRIM, Prim
    value = sum(MASK_NAMES[k] for k in mask.split("|"))
    cmd = np.array([[value,0]], np.int64)
    allow = np.ones(N_PRIM, bool)
    assert rows_allowed(cmd, allow).tolist() == [True]
    allow[int(getattr(Prim, primitive))] = False
    assert rows_allowed(cmd, allow).tolist() == [False]


def test_family_native_drafts_share_only_read_only_tables():
    from ssbot.combat import knife_chain_slam as family
    r = family.load_runner()
    digest = table_digest(r.chains)
    s = state(100); s["hero"].update(pos=[27.,4.568], vel=[0.,0.])
    q = r.preview(100,s,True,t_game=1., static_context=(r.chains,r.P,r.cfg0,r.binding,r.anchor.chains,r.anchor.cfg))
    assert q.draft.chains is r.chains and q.draft.P is r.P
    assert q.draft.anchor is not r.anchor and r.run is None
    assert table_digest(r.chains) == digest
    if q.draft.run is not None:
        q.draft.run.v["k"] = -999
        assert r.run is None
    with pytest.raises(ValueError, match="static context"):
        r.preview(100,s,True, static_context=(s,))



def test_native_continuations_are_real_ordinary_templates_with_one_bound_first_key():
    a = audit(); seed(a)
    a.begin(state(100)); a.prepare(state(100), ground=True, accepting=True, sim=SimpleNamespace(fo=100,f=100))
    R = MASK_NAMES["R"]
    ordinary = np.array([[R,R,0,0], [R,R,1,1], [R,R,1,1], [0,0,0,0]], np.int64)
    rows, names = a.rows(T=4, origin=100, prefix=np.array([0]), hold=hold(), hero_state=np.zeros(3),
                         completions=ordinary)
    assert rows.tolist() == [[R,R,0,0], [R,R,1,1]]
    assert len(names) == 2 and (rows[:,0] == a._offer.desired_mask).all()
    assert a._draft.run.sent == [(102,R)] and a.runner.run is None
    a.register_candidate(10); a.register_candidate(11)
    a.planner_result(SimpleNamespace(idx=11,mask=R,name=names[1]))
    a.final("plan",R)
    episode._act(wire_link(a),100,SimpleNamespace(chain_native=a,act=lambda s,tap:R,action_flags=0),state(100),None)
    assert a.runner.run.sent == [(102,R)]  # Never send or commit the hypothetical completion.


def test_same_strike_recertifies_each_tick_from_actual_prefix_receipts():
    def counting():
        return runner(table([{"do":"set", "set":{"a":{"add":["var.a",1]}}}]))
    a = audit(factory=counting); seed(a)
    R = MASK_NAMES["R"]
    for f in range(100,103):
        s = state(f)
        if f >= 102: s["act"] = {"target":102,"applied":102,"mask":R,"hf":{"desired":R}}
        episode._act(wire_link(a),f,Policy(a),s,None)
        assert a.runner.run.v["a"] == 2 + f - 100
    assert a.runner.run.sent == [(102,R),(103,R),(104,R)]
    assert a.counts["chain_proposal"] == a.counts["chain_intent_committed"] == 3
    assert a.counts["chain_application_observed"] == 1



def test_native_external_entry_reuses_binding_with_fresh_history_state(monkeypatch):
    from ssbot.combat import knife_chain_slam as family
    a = audit(factory=family.load_runner); seed(a)
    s = state(100); s["hero"].update(pos=[27.,4.568], vel=[0.,0.]); s["ents"][0]["pos"]=[30.,4.]
    a.begin(s); a.prepare(s,ground=True,accepting=True,sim=SimpleNamespace(fo=100,f=100))
    digest = table_digest(a.runner.chains)
    def no_rebind(*args, **kwargs):
        raise AssertionError("bound history tables must not be copied/rebound inside the tick")
    monkeypatch.setattr(family.CV.ChainRunner,"__init__",no_rebind)
    ordinary=np.array([[0,0,0],[0,1,0]],np.int64)
    result=a.rows(T=3,origin=100,prefix=np.array([0]),hold=hold(),hero_state=np.zeros(1),completions=ordinary)
    assert result is not None and a._draft.run.entered is not None
    assert a.runner.run is None and table_digest(a.runner.chains)==digest


@pytest.mark.parametrize("sent,expected", [({10:2}, []), ({8:0,10:2}, []), ({9:0,10:2}, [10])])
def test_external_history_never_infers_a_press_across_an_unknown_target(sent,expected):
    from ssbot.combat.knife_chain_history import HistView
    hist=HistView([],sent,20)
    assert hist.edges(2,{"first_tick":8})==expected



def test_queued_hook_blocks_ordinary_motion_without_rewriting_the_prefix():
    a=audit();a.begin(state(99));a.final("claw",MASK_NAMES["CLAW"])
    a.before_send(frame=99,target=101,mask=MASK_NAMES["CLAW"],flags=0,received_frame=99)
    a.sent()
    a.begin(state(100));a.prepare(state(100),ground=True,accepting=True,sim=SimpleNamespace(fo=100,f=100))
    prefix=np.array([MASK_NAMES["CLAW"]])
    assert a.rows(T=3,origin=100,prefix=prefix,hold=hold(),hero_state=np.zeros(1)) is None
    assert prefix.tolist()==[MASK_NAMES["CLAW"]] and a.dispatch.sent_for(101).desired_mask==MASK_NAMES["CLAW"]
    assert any("queued hook" in e.get("reason","") for e in a.events)


@pytest.mark.parametrize("hero2,crest,strict", [(False,"Wanderer",False), (True,"Reaper",False),
                                               (True,"Wanderer",True)])
def test_production_activation_rejects_wrong_physics_crest_or_paused_generator(monkeypatch,hero2,crest,strict):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    from ssbot.knowledge import kinematics as k
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_NATIVE","1")
    monkeypatch.setenv("SSBOT_FORUM_KNIFE_ROWS","1" if strict else "0")
    monkeypatch.setattr(k,"hero2_on",lambda:hero2)
    policy=ForumPlannerPolicy.__new__(ForumPlannerPolicy);policy.crest=crest
    with pytest.raises(ValueError):policy._reset_chain_native()



def test_episode_reset_reuses_binding_but_discards_history_and_private_state():
    calls=[]
    def factory():
        calls.append(1)
        return runner()
    a=audit(factory=factory);seed(a)
    episode._act(wire_link(a),100,Policy(a),state(100),None)
    bound=a.runner.binding;tables=a.runner.chains
    assert a.runner.anchor.hist is not None
    for episode_id in (2,3,4):
        a.reset(episode_id,start_frame=10)
        assert a.runner.binding is bound and a.runner.chains is tables
        assert a.runner.run is None and a.runner.done==[] and a.runner.fired=={}
        assert a.runner.anchor.hist is None and a.runner.anchor.external is False
        assert not a._receipts and not a._pending and not a._ticks and a._context is None
        assert a.dispatch.sent_for(102) is None and a.counts=={}
    assert len(calls)==1


def test_production_policy_reuses_bound_native_controller_across_episodes(monkeypatch,tmp_path):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy
    from ssbot.combat import knife_chain_slam as family
    from ssbot.knowledge import kinematics as k
    calls=[]
    def factory():
        calls.append(1)
        return runner()
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_NATIVE","1")
    monkeypatch.setenv("SSBOT_FORUM_CHAIN_PROBE","offline:binding-reuse")
    monkeypatch.setenv("SSBOT_FORUM_KNIFE_ROWS","0")
    monkeypatch.setattr(k,"hero2_on",lambda:True)
    monkeypatch.setattr(family,"load_runner",factory)
    policy=ForumPlannerPolicy.__new__(ForumPlannerPolicy)
    policy.crest="Wanderer";policy.log_path=tmp_path/'decisions_i0.jsonl'
    policy.planner=SimpleNamespace(chain_native=None);policy.link=SimpleNamespace(frame=90)
    policy.episode=0;policy.chain_native=None
    policy._reset_chain_native();native=policy.chain_native
    episode._act(wire_link(native),100,Policy(native),state(100),None)
    policy.episode=1;policy.link.frame=200;policy._reset_chain_native()
    assert policy.chain_native is native and policy.planner.chain_native is native
    assert len(calls)==1 and native.episode==1 and native.last_observed==200
    assert native.dispatch.sent_for(102) is None and native.counts=={}
    monkeypatch.setenv("SSBOT_FORUM_SLAM_PLAY_SET","new-configuration")
    policy.episode=2
    with pytest.raises(ValueError,match="configuration changed"):
        policy._reset_chain_native()
    assert len(calls)==1
