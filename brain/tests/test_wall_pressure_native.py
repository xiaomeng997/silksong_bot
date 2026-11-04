"""Wall successors own only real bounce transactions, never a wallward hold."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import knife_chain_wall_native as WN
from ssbot.combat import knife_chain_wall_pressure as W
from ssbot.combat.knife_chain_air import model_path
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_transfer import TransferGoal
from ssbot.combat.tactics.modes import GoalPrefs, WallPressure
from tests.test_source_tail_admission import fixture


def entered(monkeypatch, kind='stomp'):
    n,s,sim,fc,_,_=fixture(monkeypatch)
    n._wall_pressure=None
    n._transfer_goal=TransferGoal(7,7,1000,.1,'BOUNCE',MoveInstance(7,946,'CC_SLAM'))
    n._clock=1.
    s['hero']['cstate_int']=[0,8]
    s['ev']=[{'k':'hit','f':1000,'d':{'ent':7,'src':'DownSlash'}}]
    prefs=GoalPrefs(mode='RUSH',stance_x=25.,weights={},target=7,
        wall_pressure=WallPressure(7,kind,1,(25.,27.) if kind=='side' else None))
    return n,s,sim,fc,prefs


def offer_fixture(monkeypatch, kind='stomp', *, blocked=False, no_exit=False):
    n,s,sim,fc,p=entered(monkeypatch,kind)
    assert WN.prepare_goal(n,s,p,handoff=True)
    got=[]
    class Geo:
        def __init__(self,*a):pass
        def scan(self,path):
            got.append(path)
            return NS(complete=True,contacts=[NS(frame=1003)] if blocked else [])
        def preflight(self,path):
            return NS(complete=True,contacts=[NS(frame=1003)] if blocked else [])
    monkeypatch.setattr(WN,'B2Geometry',Geo)
    monkeypatch.setattr(W,'_wall_free',lambda *a:True)
    monkeypatch.setattr(W,'_terrain',lambda *a:((25.,27.),3.,30.,np.zeros((1,3))))
    def proposal(sim,state,game,intent,plan,**kw):
        cmd=np.zeros(12,np.int64)
        if kind=='stomp':cmd[:3]=[B['D']|B['A'],B['D'],B['D']]
        contact=state['f']+13 if kind=='stomp' else None
        press=state['f']+2 if kind=='stomp' else None
        path=model_path(sim,replace(plan,press_k=None if press is None else 2,contact_frame=contact),cmd,game)
        return W.PressureProposal(kind,state['f']+2,cmd,path,contact,
            state['f']+10 if kind=='side' else None,(25.,27.) if kind=='side' else None,'test_finite',press)
    monkeypatch.setattr(W,'propose',proposal)
    monkeypatch.setattr(n,'_observed_transfer_move',lambda *a:None)
    monkeypatch.setattr(n,'_query',lambda *a,**kw:[NS(frame=1003)] if blocked else [])
    monkeypatch.setattr(n,'_continuations',lambda *a,**kw:NS(verdict='fail' if no_exit else 'pass'))
    return n,s,sim,fc,p,got


def test_native_goal_preferences_consumes_real_same_focus_bounce(monkeypatch):
    n,s,sim,fc,p=entered(monkeypatch)
    out=n.goal_preferences(s,p,handoff=True)
    assert out is not p and n._wall_pressure['intent'].target==7
    assert n._wall_pressure['stroke']==0 and n.commitment is None
    assert n._wall_pressure['proposal'] is None and not n._wall_pressure['sent']


@pytest.mark.parametrize('missing',['hit','bounce','same_target','handoff','entry','no_hit'])
def test_no_wall_intent_without_same_target_actual_boundary(monkeypatch,missing):
    n,s,sim,fc,p=entered(monkeypatch)
    handoff=True
    if missing=='hit':s['ev']=[]
    if missing=='bounce':s['hero']['cstate_int']=[0,0]
    if missing=='same_target':p.target=8
    if missing=='handoff':handoff=False
    if missing=='entry':p.entry_attack=object()
    if missing=='no_hit':p.no_hit=frozenset({7})
    assert not WN.prepare_goal(n,s,p,handoff=handoff)
    assert n._wall_pressure is None and n.commitment is None


def test_proposal_does_not_claim_a_send_or_actual_future_bounce(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    offer=WN.propose(n,s,1.,sim,fc,p,False)
    assert offer is not None and offer.details['wall_pressure']
    assert not n._wall_pressure['sent'] and n.commitment is None
    assert n.post_context is None and n._press is None and n._hit is None
    assert offer.move.family=='RUNE_TRANSFER' and offer.move.antic_frame==1000
    assert n._transfer_responsibility[offer.move][0]==MoveInstance(7,946,'CC_SLAM')


@pytest.mark.parametrize('blocked,no_exit',[(True,False),(False,True)])
def test_full_contact_and_continuation_failures_do_not_send(monkeypatch,blocked,no_exit):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch,blocked=blocked,no_exit=no_exit)
    assert WN.propose(n,s,1.,sim,fc,p,False) is None
    assert n.commitment is None and n._wall_pressure is None
    assert n._failure_exposures  # actual old own bounce, not a fabricated new send


def test_successful_sent_is_only_commit_boundary(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    s.update(dt=1/60);s['act'].update(target=1000,applied=1000,mask=int(sim.prefix[0]))
    n.begin(s);n._clock=1.;n._clock_known=True
    # begin only observes real state; retain entered context and exact current sim.
    n._context=((1000,s,1.,False,True),sim,None,None)
    offer=WN.propose(n,s,1.,sim,fc,p,False);assert offer is not None
    planner=NS(measurement_enabled=False,jump_until=-1,macro_until=-1)
    result=n.install(offer,planner);n.planner_result(result);n.final('plan',offer.mask)
    n.before_send(frame=1000,target=1002,mask=offer.mask,flags=0,received_frame=1000)
    assert n.commitment is None and not n._wall_pressure['sent']
    sent=n.sent()
    assert sent.chain_outcome=='sent' and n._wall_pressure['sent']
    assert n.commitment['move']==offer.move and n._press==1002


def test_marker_only_cannot_advance_a_stroke_and_new_real_bounce_can(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    ctx=n._wall_pressure
    s2=deepcopy(s);s2['f']=1013;s2['ev']=[]
    n.post_context=None
    assert WN.prepare_goal(n,s2,p,handoff=True)
    assert ctx['stroke']==0
    n._hit=1012
    n.post_context={'move':MoveInstance(7,1000,'RUNE_TRANSFER'),'bounce':1013,'hit':1012,'press':1002}
    monkeypatch.setattr(n,'_observed_transfer_move',lambda *a:(MoveInstance(7,1009,'CC_SLAM'),1.15))
    assert WN.prepare_goal(n,s2,p,handoff=True)
    assert ctx['stroke']==1 and ctx['bounce']==1013 and ctx['proposal'] is None
    assert ctx['goal'].responsibility==MoveInstance(7,1009,'CC_SLAM')
    assert n.commitment is None and n.post_context is None


def test_ground_handoff_waits_for_observed_ground_and_keeps_old_tail(monkeypatch):
    n,s,sim,fc,p,got=offer_fixture(monkeypatch,'side')
    first=WN.propose(n,s,1.,sim,fc,p,False);assert first is not None
    n._wall_pressure['sent']=True
    n.commitment={'move':first.move,'origin':1000,'ta':.1}
    from ssbot.knowledge import kinematics as K
    sim.start.reshape(K.K)[K.GROUND]=1.
    monkeypatch.setattr(WN.T,'bounce_tail_pending',lambda *a:True)
    assert WN.propose(n,s,1.,sim,fc,p,True) is None
    assert n._wall_pressure['landing'] and n.commitment is None
    assert n._wall_pressure is not None  # retains old hammer responsibility
    monkeypatch.setattr(WN.T,'bounce_tail_pending',lambda *a:False)
    assert WN.propose(n,s,1.,sim,fc,p,True) is None
    assert n._wall_pressure is None and n.runner.run is None


def test_target_handoff_does_not_ignore_old_hammer(monkeypatch):
    n,s,sim,fc,p=entered(monkeypatch)
    assert WN.prepare_goal(n,s,p,handoff=True)
    p.target=8
    n._press=1002  # an already sent strike still waits for its real result
    n.commitment={'move':MoveInstance(7,1000,'RUNE_TRANSFER')}
    monkeypatch.setattr(WN.T,'bounce_tail_pending',lambda *a:True)
    assert WN.prepare_goal(n,s,p,handoff=True) and n._wall_pressure is not None
    monkeypatch.setattr(WN.T,'bounce_tail_pending',lambda *a:False)
    assert WN.prepare_goal(n,s,p,handoff=True) and n._wall_pressure is not None
    assert n.commitment is not None  # old hammer-off cannot cancel an in-flight own knife


def test_no_l2_wall_successor_never_holds_a_wallward_tail(monkeypatch):
    n,s,sim,fc,scans,short=fixture(monkeypatch)
    s['ents'][0]['fsms'][0].update(state='Slam Antic',t=0.)
    fc.rs.trk.now[7][2].s=-1
    offer=n._transfer_offer(s,1.,sim,fc,NS(target=8),False)
    assert offer is not None and offer.mask==0
    assert np.all(scans[0].commands[1:]==0)


@pytest.mark.parametrize('withdraw',['target','no_hit','entry','intent'])
def test_withdrawn_l2_intent_yields_keys_but_keeps_residual_without_new_knife(monkeypatch,withdraw):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    if withdraw=='target':p.target=8
    if withdraw=='no_hit':p.no_hit=frozenset({7})
    if withdraw=='entry':p.entry_attack=object()
    if withdraw=='intent':p.wall_pressure=None
    assert not WN.prepare_goal(n,s,p,handoff=True)
    assert n._wall_pressure['yielded'] and n.commitment is None
    assert n.residual_context()['input_owner'] is False
    assert n.runner.run is None


def test_conditional_pogo_is_not_used_for_precontact_admission(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    seen=[]
    def query(forecast,move,path,**kw):
        seen.append(path)
        assert not (path.assumptions or {}).get('conditional_contact_only')
        assert path.contact_frame is None or path.end!='bounce'
        return []
    monkeypatch.setattr(n,'_query',query)
    offer=WN.propose(n,s,1.,sim,fc,p,False)
    assert offer is not None and len(seen)==2


def test_residual_end_does_not_cancel_different_new_commitment(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    p.target=8
    assert not WN.prepare_goal(n,s,p,handoff=True)
    new={'move':MoveInstance(8,1001,'CC_SLAM'),'origin':1001}
    n.commitment=new
    monkeypatch.setattr(WN.T,'bounce_tail_pending',lambda *a:False)
    assert not WN.prepare_goal(n,s,p,handoff=True)
    assert n._wall_pressure is None and n.commitment is new


def test_ordinary_send_keeps_explicit_residual_damage_responsibility(monkeypatch):
    n,s,sim,fc,p=entered(monkeypatch,'side')
    assert WN.prepare_goal(n,s,p,handoff=True)
    n._wall_pressure['landing']=True
    s.update(dt=1/60);s['act'].update(target=1000,applied=1000,mask=int(sim.prefix[0]))
    n.begin(s);n._clock=1.;n._clock_known=True
    n.final('ordinary',0)
    n.before_send(frame=1000,target=1002,mask=0,flags=0,received_frame=1000)
    n.sent()
    assert n.runner.run is None and n.commitment is None
    assert n.residual_context()['source_move']=={'target_iid':7,'antic_frame':946,'family':'CC_SLAM'}
    n._budget_hp=7;n._last_budget_f=999
    s['hero']['health']=6
    notes=[];monkeypatch.setattr(n,'_note',lambda event,**kw:notes.append((event,kw)))
    n.observe_learning(s)
    losses=[data for event,data in notes if event=='b2_hp_loss']
    assert len(losses)==1 and losses[0]['chain_related'] and losses[0]['phase']=='residual'
    assert losses[0]['residual_context']['input_owner'] is False


def test_physical_side_refinement_uses_existing_ground_slash_ranking(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch,'side')
    assert WN.propose(n,s,1.,sim,fc,p,False) is not None
    out=WN.preferences(n,p)
    assert out.wall_pressure.kind=='side' and 7 in out.ground_first
    assert 7 in out.ground_hit and out.hit_kw[7][3]==0
    assert out.target==p.target


def test_blocked_landing_can_choose_rear_knife_without_repeating_landing(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch,'side')
    first_factory=W.propose
    kinds=[]
    def choose(sim,state,game,intent,plan,*,allow_landing=True,**kw):
        q=first_factory(sim,state,game,intent,plan,**kw)
        kinds.append(allow_landing)
        if allow_landing:return q
        return replace(q,kind='stomp',contact_frame=state['f']+13,
                       press_frame=state['f']+2,landing_frame=None)
    monkeypatch.setattr(W,'propose',choose)
    monkeypatch.setattr(WN.B2Geometry,'scan',lambda *a:NS(complete=True,contacts=[NS(frame=1003)]))
    result=WN.propose(n,s,1.,sim,fc,p,False)
    assert result is not None and result.details['kind']=='stomp'
    assert kinds==[True,False]
    assert n.commitment is None


def at_frame(sim,state,frame):
    from ssbot.combat.air_chain import ChainSim
    s=deepcopy(state);s['f']=frame
    return s,ChainSim(sim.start,sim.prefix,sim.hold,sim.params,sim.terrain,frame,frame)


@pytest.mark.parametrize('observed_frame',[1012,1013,1014,1015])
def test_contact_row_waits_for_next_real_state_without_false_early_end(monkeypatch,observed_frame):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    first=WN.propose(n,s,1.,sim,fc,p,False);assert first is not None
    n._wall_pressure['sent']=True;n._press=1002
    late,current=at_frame(sim,s,observed_frame)  # contact1013; observe through1015, target through1017
    result=WN.propose(n,late,1.2,current,fc,p,False)
    assert result is not None and result.stage=='active' and result.mask==0
    assert n.post_context is None and n._hit is None


def test_no_late_press_or_unobserved_contact_can_slide_absolute_row(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    assert WN.propose(n,s,1.,sim,fc,p,False) is not None
    n._wall_pressure['sent']=True
    late,current=at_frame(sim,s,1001)
    assert WN.propose(n,late,1.1,current,fc,p,False) is None
    assert n._wall_pressure is None


def test_missing_expected_contact_ends_finite_observation_grace(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    assert WN.propose(n,s,1.,sim,fc,p,False) is not None
    n._wall_pressure['sent']=True;n._press=1002
    late,current=at_frame(sim,s,1016)
    assert WN.propose(n,late,1.2,current,fc,p,False) is None
    assert n._wall_pressure is None and n._failure_exposures


def test_failed_source_cannot_restart_same_wall_successor(monkeypatch):
    n,s,sim,fc,p=entered(monkeypatch)
    n._failed_hook_moves.add(n._transfer_goal.responsibility)
    assert not WN.prepare_goal(n,s,p,handoff=True)
    assert n._wall_pressure is None


def test_hit_without_actual_bounce_cannot_outlive_contact_observation_grace(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    assert WN.propose(n,s,1.,sim,fc,p,False) is not None
    n._wall_pressure['sent']=True;n._press=1002;n._hit=1013
    late,current=at_frame(sim,s,1016)
    assert WN.propose(n,late,1.2,current,fc,p,False) is None
    assert n._wall_pressure is None and n._failure_exposures


def test_wall_gap_side_intent_never_reopens_a_fresh_vault_stomp(monkeypatch):
    n,s,sim,fc,p=entered(monkeypatch,'side')
    n._wall_pressure=None;n.vault_enabled=True;n._vault_ready=True
    n._context=((1000,s,1.,True,True),sim,None,None)
    from ssbot.combat import knife_chain_vault_native as V
    monkeypatch.setattr(V,'propose',lambda *a:pytest.fail('wall gap side borrowed a fresh vault'))
    assert n._propose(None,None,None,None,None,fc,p,None) is None
    assert n.commitment is None and n.runner.run is None


def test_external_ground_flag_alone_cannot_claim_physical_landing(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch,'side')
    from ssbot.knowledge import kinematics as K
    assert sim.start.reshape(K.K)[K.GROUND]==0
    offer=WN.propose(n,s,1.,sim,fc,p,True)
    assert offer is not None and not n._wall_pressure['landing']


def test_gap_handoff_uses_physical_x_instead_of_rendered_x(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch,'side')
    first=WN.propose(n,s,1.,sim,fc,p,False);assert first is not None
    n._wall_pressure['sent']=True
    from ssbot.knowledge import kinematics as K
    sim.start.reshape(K.K)[K.GROUND]=1.
    s['hero']['pos'][0]=100.  # deliberately stale rendering, not physical S0
    monkeypatch.setattr(WN.T,'bounce_tail_pending',lambda *a:True)
    assert WN.propose(n,s,1.,sim,fc,p,True) is None
    assert n._wall_pressure['landing']


def test_current_slam_missing_or_changed_clock_cannot_use_stale_wall_permission(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    fc.rs.trk.now[7][2].t0=10.  # current instance no longer matches the causal source
    assert WN.propose(n,s,1.,sim,fc,p,False) is None
    assert n._wall_pressure is None and n._failure_exposures


def test_known_raw_slam_cannot_use_another_trackers_clock(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    monkeypatch.setattr(n,'_observed_transfer_move',lambda *a:(MoveInstance(7,946,'CC_SLAM'),.1))
    fc.rs.trk.now[7][2].t0=10.
    assert WN.propose(n,s,1.,sim,fc,p,False) is None
    assert n._wall_pressure is None and n._failure_exposures


@pytest.mark.parametrize('proof',['entity','hit'])
def test_confirmed_source_death_releases_residual_but_not_new_target_commitment(monkeypatch,proof):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    p.target=8
    assert not WN.prepare_goal(n,s,p,handoff=True)
    new={'move':MoveInstance(8,1001,'CC_SLAM'),'origin':1001}
    n.commitment=new
    monkeypatch.setattr(WN.T,'bounce_tail_pending',lambda *a:True)
    if proof=='entity':s['ents'][0]['is_dead']=True
    else:s['ev']=[{'k':'hit','f':1000,'d':{'ent':7,'src':'DownSlash','dead':True}}]
    assert not WN.prepare_goal(n,s,p,handoff=True)
    assert n._wall_pressure is None and n.commitment is new


def test_missing_source_is_not_a_fabricated_death_boundary(monkeypatch):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch)
    p.target=8
    assert not WN.prepare_goal(n,s,p,handoff=True)
    s['ents']=[e for e in s['ents'] if e['iid']!=7];s['ev']=[]
    monkeypatch.setattr(WN.T,'bounce_tail_pending',lambda *a:True)
    assert not WN.prepare_goal(n,s,p,handoff=True)
    assert n._wall_pressure is not None and n.residual_context() is not None


@pytest.mark.parametrize('kind',['side','stomp'])
def test_checked_wall_successor_table_reproduces_absolute_row(monkeypatch,kind):
    n,s,sim,fc,p,_=offer_fixture(monkeypatch,kind)
    offer=WN.propose(n,s,1.,sim,fc,p,False);assert offer is not None
    from ssbot.combat.knife_chain_eval import X
    from ssbot.combat.knife_chain_nominal import NominalUnsupported
    row=offer.draft.run.v['row']
    for i,expected in enumerate(row['masks']):
        obs=NS(f=row['F0']+i-2,F=row['F0']+i,k=i+2,target_valid=True,ground=False,bounced=False)
        actual=offer.draft.eval_link(X(offer.draft,offer.draft.run,obs))
        assert actual==expected
    obs=NS(f=row['F0']+len(row['masks'])-2,F=row['F0']+len(row['masks']),k=100,
           target_valid=True,ground=False,bounced=False)
    with pytest.raises(NominalUnsupported):
        offer.draft.eval_link(X(offer.draft,offer.draft.run,obs))
