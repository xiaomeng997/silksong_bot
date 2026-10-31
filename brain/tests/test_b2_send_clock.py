"""Local receive-clock dispatch estimates never count as action acceptance."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from ssbot.combat.knife_chain_deadline import first_jump_clock,FRAME_NS
from ssbot.combat.knife_chain_budget import LearningStop
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.train.measurement import MeasurementTrace
from ssbot.train import episode
from tests.test_b2_deferred_dispatch_guard import deferred,stage,ORIGIN,MOVE


def timing(now,anchor=3):
    return {"now_ns":now,"anchor_frame":ORIGIN+anchor,"anchor_ns":100_000_000,"latest_received_frame":ORIGIN+anchor}


def test_previous_state_has_13ms_window_with_send_reserve():
    assert not first_jump_clock(timing(111_999_999),ORIGIN+4)["late"]
    r=first_jump_clock(timing(112_000_000),ORIGIN+4)
    assert r["late"] and r["remaining_ns"]==0 and r["estimated_finish_ns"]==113_000_000


def test_second_previous_state_projects_only_one_extra_frame():
    r=first_jump_clock(timing(111_999_999,2),ORIGIN+4)
    assert not r["late"] and r["deadline_ns"]==113_000_000+FRAME_NS


@pytest.mark.parametrize("patch",[{"now_ns":None},{"anchor_ns":True},{"anchor_frame":ORIGIN+1},
 {"anchor_frame":ORIGIN+4},{"anchor_frame":ORIGIN+5},{"anchor_ns":-1},{"now_ns":99_999_999}])
def test_unknown_future_old_or_inconsistent_clocks_are_not_safe(patch):
    t=timing(101_000_000);t.update(patch)
    with pytest.raises(ValueError):first_jump_clock(t,ORIGIN+4)


def test_receive_snapshot_prefers_previous_state_and_changes_no_records():
    m=MeasurementTrace(clock_ns=lambda:120_000_000);m.start_episode(0)
    m.received(ORIGIN+2,2,90_000_000);m.received(ORIGIN+3,3,100_000_000)
    m.received(ORIGIN+4,4,116_000_000)
    before=(deepcopy(m._rows),deepcopy(m._received))
    assert m.send_timing(ORIGIN+4)=={**timing(120_000_000),"earlier_frame":ORIGIN+2,"earlier_ns":90_000_000,"latest_received_frame":ORIGIN+4}
    assert before==(m._rows,m._received)


def test_receive_snapshot_does_not_project_from_unknown_old_or_future_frames():
    m=MeasurementTrace(clock_ns=lambda:120_000_000)
    m.received(ORIGIN+1,1,80_000_000);m.received(ORIGIN+4,4,116_000_000)
    assert m.send_timing(ORIGIN+4) is None


def test_first_J_is_vetoed_before_target_STATE_arrives_when_time_expires():
    n=deferred();n.require_send_clock=True;watch=n._jump_start
    stage(n,ORIGIN+2,B["J"])
    assert n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B["J"],flags=0,
                         received_frame=ORIGIN+3,dispatch_clock=timing(112_100_000))==0
    assert not watch.sent_targets and MOVE in n._failed_hook_moves
    assert n.sent().desired_mask==0 and len(n._failure_exposures)==1
    row=next(x for x in n.events if x["event"]=="b2_jump_dispatch_clock")
    assert row["late"] and row["remaining_ns"]<0


def test_timely_first_J_still_needs_real_takeoff_after_send():
    n=deferred();n.require_send_clock=True;stage(n,ORIGIN+2,B["J"])
    assert n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B["J"],flags=0,
                         received_frame=ORIGIN+3,dispatch_clock=timing(111_000_000)) is None
    n.sent();assert n._jump_start.sent_targets=={ORIGIN+4} and n._jump_start.seen_frame is None


def test_required_runtime_clock_missing_stops_instead_of_claiming_safe():
    n=deferred();n.require_send_clock=True;stage(n,ORIGIN+2,B["J"])
    with pytest.raises(LearningStop,match="missing critical first-J receive clock"):
        n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B["J"],flags=0,received_frame=ORIGIN+2)
    assert not n._jump_start.sent_targets


def test_a_later_J_hold_does_not_need_a_new_first_edge_deadline():
    n=deferred();n.require_send_clock=True;stage(n,ORIGIN+2,B["J"])
    n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B["J"],flags=0,
                  received_frame=ORIGIN+3,dispatch_clock=timing(111_000_000));n.sent()
    stage(n,ORIGIN+3,B["J"])
    assert n.before_send(frame=ORIGIN+3,target=ORIGIN+5,mask=B["J"],flags=0,received_frame=ORIGIN+3) is None


def test_episode_passes_clock_only_to_B2_and_records_actual_send():
    seen={};sent=[]
    class Chain:
        b2=True
        def before_send(self,**kwargs):seen.update(kwargs)
        def sent(self):sent.append(True)
    m=MeasurementTrace(clock_ns=lambda:111_000_000);m.received(ORIGIN+3,3,100_000_000)
    acts=[]
    link=NS(measurement=m,frame=ORIGIN+3,act=lambda *a,**k:acts.append((a,k)))
    policy=NS(chain_native=Chain(),act=lambda *a:B["J"])
    episode._act(link,ORIGIN+2,policy,{},None)
    assert seen["dispatch_clock"]==timing(111_000_000)
    assert sent==[True] and acts[0][0]==(ORIGIN+4,B["J"])


def test_environment_runtime_requires_receive_clock_across_resets(monkeypatch,tmp_path):
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    from tests.test_knife_chain_b2 import runner
    from ssbot.combat import knife_chain_slam,attack_range
    monkeypatch.setattr(knife_chain_slam,"load_runner",runner)
    monkeypatch.setattr(attack_range,"load_table",lambda **k:NS(meta={"hammer_polygon_revision":"test"}))
    for key,value in {"SSBOT_FORUM_CHAIN_BATCH":"clock-test","SSBOT_FORUM_CHAIN_ARM":"B","SSBOT_FORUM_CHAIN_PROBE":"clock-test",
                      "SSBOT_FORUM_CHAIN_BUDGET":str(tmp_path/"budget.json")}.items():monkeypatch.setenv(key,value)
    n=NativeChainB2.from_env(journal=tmp_path/"chain.jsonl")
    assert n.require_send_clock
    n.reset(1);assert n.require_send_clock


def test_a_delayed_previous_STATE_cannot_extend_the_earlier_projection():
    t={**timing(105_000_000),"earlier_frame":ORIGIN+2,"earlier_ns":74_000_000}
    r=first_jump_clock(t,ORIGIN+4)
    assert r["late"] and r["deadline_ns"]==74_000_000+13_000_000+FRAME_NS
    assert r["deadline_anchor_frame"]==ORIGIN+2


def test_earlier_projection_cannot_extend_a_tighter_previous_STATE_deadline():
    t={**timing(111_000_000),"earlier_frame":ORIGIN+2,"earlier_ns":99_000_000}
    r=first_jump_clock(t,ORIGIN+4)
    assert not r["late"] and r["deadline_ns"]==113_000_000


def test_inconsistent_second_anchor_is_not_ignored():
    with pytest.raises(ValueError,match="earlier receive anchor"):
        first_jump_clock({**timing(111_000_000),"earlier_frame":ORIGIN+2,"earlier_ns":100_000_001},ORIGIN+4)


def test_receive_thread_target_seen_prevents_J_even_if_link_frame_is_stale():
    n=deferred();n.require_send_clock=True;stage(n,ORIGIN+2,B["J"])
    t={**timing(101_000_000),"latest_received_frame":ORIGIN+4}
    assert not first_jump_clock(t,ORIGIN+4)["remaining_ns"]<0
    assert first_jump_clock(t,ORIGIN+4)["target_already_received"]
    assert n.before_send(frame=ORIGIN+2,target=ORIGIN+4,mask=B["J"],flags=0,
                         received_frame=ORIGIN+3,dispatch_clock=t)==0
    assert n.sent().desired_mask==0


def test_latest_receive_cannot_precede_its_own_clock_anchor():
    with pytest.raises(ValueError,match="inconsistent"):
        first_jump_clock({**timing(101_000_000),"latest_received_frame":ORIGIN+2},ORIGIN+4)


def test_actual_episode_clock_veto_sends_neutral_packet_and_binds_receipt():
    import msgpack
    from ssbot.ipc.framing import HEADER
    from tests.test_knife_chain_native import wire_link
    n=deferred();n.require_send_clock=True;stage(n,ORIGIN+2,B["J"])
    link=wire_link(n);link._state={"f":ORIGIN+3}
    trace=MeasurementTrace(clock_ns=lambda:112_100_000)
    trace.received(ORIGIN+2,2,90_000_000);trace.received(ORIGIN+3,3,100_000_000)
    link.measurement=trace
    policy=NS(chain_native=n,act=lambda *a:B["J"],sent={ORIGIN+4:B["J"]})
    episode._act(link,ORIGIN+2,policy,{},None)
    payload=msgpack.unpackb(link.packets[-1][HEADER.size:])
    assert payload[:3]==[ORIGIN+4,0,0]
    assert policy.sent[ORIGIN+4]==n._receipts[ORIGIN+4]==0
    assert policy.measurement_choice["owner"]=="b2_deadline_abort"
    assert n.commitment is None and len(n._failure_exposures)==1
