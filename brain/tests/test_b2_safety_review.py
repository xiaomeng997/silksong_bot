"""Retained review safeguards on the single-tick B2, without staged launch.
Transaction fixtures do not certify live physical trajectories.
"""
from types import SimpleNamespace
import pytest
from ssbot.combat.knife_chain_b2 import NativeChainB2,B2Offer
from ssbot.combat.knife_chain_budget import LearningBudget,LearningStop
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_nominal import logical_copy
from ssbot.combat.knife_chain_eval import ChainPreview
from tests.test_knife_chain_b2 import runner,raw,bits
from tests.test_b2_hook_start import commit,actual,ORIGIN
F=1000;MOVE=MoveInstance(7,F,"CC_SLAM")
def test_loss_after_abandon_is_still_first_chain_related_injury(tmp_path):
    b=LearningBudget(tmp_path/'budget.json',batch='failure-window',revision='r',worker='i0')
    n=NativeChainB2(runner_factory=runner,probe_ref='failure-window',budget=b)
    s=raw(F);n.begin(s)
    n.commitment={'move':MOVE,'origin':F,'ta':n._clock,'predicted_bounce':F+51}
    n._recover('missed planned action',F)
    assert n.runner.run is None and n.commitment is None and n.recovery is None
    loss=raw(F+3);loss['hero']['health']=6;loss['ents'][0]['fsms'][0].update(state='Slam 2',t=.02)
    with pytest.raises(LearningStop):n.observe_learning(loss)
    event=next(e for e in n.events if e['event']=='b2_hp_loss')
    assert event['chain_related'] and event['phase']=='recovery_after_failure'
    assert b.state['b_fight_hp']==1 and b.state['stop'] is not None

def test_a_arm_never_enables_strict_table_observations():
    n=NativeChainB2(runner_factory=runner,probe_ref='A',arm='A')
    assert n.runner.anchor.b2_strict_observations is False

def test_known_too_late_application_is_covered_but_not_called_skipped():
    n=NativeChainB2(runner_factory=runner,probe_ref='late-classification')
    n._receipts={100:1,104:2};n._pending={100:1,104:2}
    n._last_matching_report={'target':99,'desired':0,'observed':99}
    a={'f':103,'act':{'target':100,'applied':103,'hf':{'desired':1}}}
    n._observe_application(a)
    assert 100 in n._pending
    n._observe_application({'f':104,'act':{'target':104,'applied':104,'hf':{'desired':2}}})
    assert not n._pending and n._receipt_counts['late_beyond_bound']==1
    assert n._receipt_counts['skip_key_change']==0
    assert n._application[100]['kind']=='covered_late_beyond_bound'

def test_applied_grounded_slash_is_a_defect_not_a_pogo():
    from tests.test_knife_chain_b2 import native_committed,next_state
    # Explicit transaction fixture: real pressed D|A, then actual ground Slash.
    n=NativeChainB2(runner_factory=runner,probe_ref='grounded-strike')
    s=bits(raw(F),onGround=True);n.begin(s)
    n.commitment={'move':MOVE,'origin':F,'ta':0.,'predicted_bounce':F+51}
    n._press=F+2;n._receipts[F+2]=B['D']|B['A']
    s=bits(raw(F+1),onGround=True);s['act'].update(target=F,applied=F,hf={'desired':0});n.begin(s)
    s=bits(raw(F+2),onGround=True,attacking=True);s['hero']['anim']['clip']='Slash'
    s['act'].update(target=F+2,applied=F+2,mask=B['D']|B['A'],hf={'desired':B['D']|B['A']})
    n.begin(s)
    assert n.commitment is None and n.post_context is None and n._hit is None
    assert MOVE in n._failed_hook_moves and n._failure_exposures
    assert any(e['event']=='b2_controller_defect' and 'grounded Slash' in e['reason'] for e in n.events)

def test_episode_sender_keeps_actual_wire_and_prefix_after_deadline_override():
    from ssbot.train.episode import _act
    log=[]
    class Chain:
        def before_send(self,**kw):log.append(('prepared',kw));return 0
        def sent(self):log.append(('sent',))
    class Link:
        frame=F+6;measurement=None
        def act(self,target,mask,**kw):log.append(('wire',target,mask))
    class Policy:
        chain_native=Chain();action_flags=0;sent={};measurement_choice={'owner':'plan','planner_mask':B['CLAW']}
        def act(self,state,tap):return B['CLAW']
    p=Policy();_act(Link(),F+2,p,{'f':F+2},None)
    assert ('wire',F+4,0) in log and p.sent[F+4]==0
    assert p.measurement_choice['pre_send_original_mask']==B['CLAW']
    assert p.measurement_choice['owner']=='b2_deadline_abort'

def test_deadline_override_trace_keeps_intent_and_one_matching_wire_record(tmp_path):
    from ssbot.train.episode import _act
    from ssbot.train.measurement import validate_trace
    from tests.test_measurement_episode_integration import Link,Tap
    link=Link(Tap());link.frame=F+6;trace=link.measurement
    trace.received(F+2,1,trace.clock());trace.received(F+6,2,trace.clock())
    state={'f':F+2,'dt':1/60};trace.begin_tick(state)
    chain=SimpleNamespace(before_send=lambda **kw:0,sent=lambda:None)
    policy=SimpleNamespace(chain_native=chain,action_flags=0,sent={},
        measurement_choice={'owner':'plan','planner_mask':B['CLAW']},act=lambda *a:B['CLAW'])
    _act(link,F+2,policy,state,None);trace.end_tick()
    ticks=[x for x in trace._rows if x['kind']=='tick'];actions=[x for x in trace._rows if x['kind']=='action']
    assert len(ticks)==len(actions)==1
    assert ticks[0]['returned_mask']==0 and ticks[0]['planner_mask']==B['CLAW']
    assert ticks[0]['pre_send_original_mask']==B['CLAW']
    assert actions[0]['mask']==0 and actions[0]['owner']=='b2_deadline_abort'
    assert actions[0]['policy_mask_matches_wire'] is True
    out=tmp_path/'deadline.jsonl';trace.write(out);assert validate_trace(out)['complete']

@pytest.mark.parametrize("late",[2615,2616,2617])
def test_single_tick_claw_deadline_releases_on_original_target(late):
    n=commit();move=n.commitment['move']
    n.begin(actual(2612,target=2612,desired=B['J']),history=[actual(2611)])
    draft=logical_copy(n.runner)
    offer=B2Offer('active',None,draft,B['R']|B['CLAW'],0.,move,{})
    res=n.install(offer,SimpleNamespace(measurement_enabled=False));n.planner_result(res);n.final('plan',offer.mask)
    replacement=n.before_send(frame=2612,target=2614,mask=offer.mask,flags=0,received_frame=late)
    assert replacement==0 and n._prepared['target']==2614 and n._prepared['mask']==0
    assert n.commitment is None and move in n._failed_hook_moves
    n.sent();assert n._receipts[2614]==0 and n.counts['b2_hook_start_sent']==0

@pytest.mark.parametrize('gate',['low_crit','asw_crit','map2','supervisor'])
def test_critical_priority_gate_recovers_before_any_preview(monkeypatch,gate):
    n=commit();n.policy_gate_reason=gate
    monkeypatch.setattr(n,'_preview',lambda:pytest.fail('priority gate must precede preview'))
    assert n.propose(None,None,None,None,None,None,None,None) is None
    assert n.commitment is None and n.counts['b2_no_candidate']

def test_table_bounce_claim_without_real_observation_recovers(monkeypatch):
    import ssbot.combat.knife_chain_b2 as mod
    n=commit();move=n.commitment['move'];draft=logical_copy(n.runner)
    draft.run.v['bounced']=True
    n._context=((ORIGIN,n._actual_state,0.,True,True),None,None,None)
    monkeypatch.setattr(n,'_preview',lambda:(ChainPreview(ORIGIN,B['J'],draft),move))
    monkeypatch.setattr(mod,'B2Geometry',lambda *a:SimpleNamespace())
    fc=SimpleNamespace(rs=SimpleNamespace(trk=SimpleNamespace(now={7:(None,None,None)})))
    assert n.propose(None,None,None,None,None,fc,None,None) is None
    assert n.commitment is None and n.post_context is None and n.counts['b2_table_bounce_mismatch']==1
