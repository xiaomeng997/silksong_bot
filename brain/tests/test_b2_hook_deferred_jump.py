"""A planned wait before hook takeoff is modeled, never a late-send shift."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import claw_strike as cs
from tests.test_b2_hook_lead import search,adapter


def delayed_model(monkeypatch,f=1000,land_at_press=False):
    owner,sim,ctx=search(monkeypatch);sim.f=sim.fo=f;captured=[]
    def roll(cmd):
        captured.append(cmd.copy());n,T=cmd.shape
        box=np.zeros((n,T+3,4));box[:]=[34.77,4.,35.23,6.2]
        flags=np.zeros((n,T+3),np.int64)
        for j,row in enumerate(cmd):
            starts=np.flatnonzero(row & cs.M_J)
            if len(starts):flags[j,:sim.off+int(starts[0])+1]=cs.kin.F_GROUND
            if land_at_press:flags[j,sim.off+5:]=cs.kin.F_GROUND
        return NS(box=box,vel=np.zeros((n,T+3,2)),flags=flags)
    sim.roll=roll
    return owner,sim,ctx,captured


def test_initial_wait_is_in_rollout_and_absolute_plan(monkeypatch):
    owner,sim,ctx,seen=delayed_model(monkeypatch)
    p=owner.plan(sim,ctx,True,True,hop_from=1004,p_min=1007,first_feasible=True)
    assert p is not None and (p.f0,p.hop,p.f_press)==(1004,3,1007)
    assert p.var_ok==[4]*4
    for row in seen[0]:
        assert list(row[:2])==[0,0]
        assert np.array_equal(np.flatnonzero(row & cs.M_J),[2,3,4])
    assert cs.plan_mask(p,1002,1)==cs.plan_mask(p,1003,1)==0
    assert cs.plan_mask(p,1004,1)&cs.M_J
    assert cs.plan_mask(p,1007,1)&cs.M_CLAW


def test_future_jump_recheck_does_not_press_before_original_start(monkeypatch):
    owner,sim,ctx,seen=delayed_model(monkeypatch,f=1001)
    q=owner.plan(sim,ctx,False,True,hop_from=1004,hop_until=1007,p_only=1007,p_min=1007,first_feasible=True)
    assert q is not None and q.f_press==1007
    row=seen[0][0]
    assert row[0]==0 and np.array_equal(np.flatnonzero(row & cs.M_J),[1,2,3])


def test_ground_after_actual_jump_still_rejects_every_candidate(monkeypatch):
    owner,sim,ctx,seen=delayed_model(monkeypatch,land_at_press=True)
    assert owner.plan(sim,ctx,True,True,hop_from=1004,p_only=1007,p_min=1007) is None


def test_ongoing_jump_uses_only_remaining_original_hold(monkeypatch):
    owner,sim,ctx=search(monkeypatch);sim.f=sim.fo=1004;seen=[];roll=sim.roll
    sim.roll=lambda c:(seen.append(c.copy()) or roll(c))
    q=owner.plan(sim,ctx,False,True,hop_from=1004,hop_until=1007,p_only=1008,p_min=1007)
    assert q is not None
    assert np.array_equal(np.flatnonzero(seen[0][0]&cs.M_J),[0])


@pytest.mark.parametrize('bad',[True,1.5,-1,'1004'])
def test_invalid_absolute_hop_start_rejected(monkeypatch,bad):
    owner,sim,ctx=search(monkeypatch)
    with pytest.raises(ValueError,match='hop start'):
        owner.plan(sim,ctx,True,True,hop_from=bad)


def test_new_jump_cannot_start_in_past(monkeypatch):
    owner,sim,ctx=search(monkeypatch)
    with pytest.raises(ValueError,match='hop start'):
        owner.plan(sim,ctx,True,True,hop_from=1001)


def test_fixed_press_before_new_takeoff_floor_is_not_shifted(monkeypatch):
    owner,sim,ctx=search(monkeypatch)
    assert owner.plan(sim,ctx,True,True,hop_from=1004,p_only=1005,p_min=1007) is None


def test_native_b2_plans_four_frame_dispatch_lead(monkeypatch):
    from ssbot.combat.knife_chain_jump import B2_HOOK_PLAN_LEAD
    assert B2_HOOK_PLAN_LEAD==4
    kw=adapter(monkeypatch)
    assert kw['hop_from']==1004 and kw['p_min']==1007


@pytest.mark.parametrize('fixed',[None,1007])
def test_recheck_uses_original_absolute_jump_even_before_takeoff(monkeypatch,fixed):
    kw=adapter(monkeypatch,ground=False,prior=NS(f0=1004,hop=3),f=1001,p_only=fixed)
    assert kw['hop_from']==1004 and kw['hop_until']==1007 and kw['p_min']==1007
    assert kw['p_only']==fixed


def test_future_hold_recheck_cannot_hook_before_jump_even_without_extra_floor(monkeypatch):
    owner,sim,ctx,seen=delayed_model(monkeypatch,f=1001)
    assert owner.plan(sim,ctx,False,True,hop_from=1004,hop_until=1007,p_only=1004) is None
    assert not seen


def test_successful_neutral_after_veto_keeps_failed_preparation_hp_exposure():
    from tests.test_b2_hook_jump_guard import prepared,ORIGIN,MOVE,B
    n=prepared();n._press=n._accepted=n._hit=ORIGIN-10
    assert n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B['J'],flags=0,received_frame=ORIGIN+2)==0
    assert n._failure_exposures==[]  # not a sent preparation yet
    n.sent()
    assert len(n._failure_exposures)==1
    exposure=n._failure_exposures[0]
    assert exposure.move==MOVE and exposure.origin==ORIGIN and exposure.failed_frame==ORIGIN+2
    assert exposure.active(ORIGIN+32) and exposure.through is None
    assert n._press is n._accepted is n._hit is None
    event=next(x for x in n.events if x['event']=='b2_failure_exposure')
    assert event['source']=='successful neutral replacement after initial dispatch veto'


def test_no_exposure_is_claimed_without_successful_neutral_send():
    from tests.test_b2_hook_jump_guard import prepared,ORIGIN,B
    n=prepared();n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B['J'],flags=0,received_frame=ORIGIN+2)
    assert n._failure_exposures==[]
    n.reset(1)
    assert n._vetoed_preparation is None and n._failure_exposures==[]


def test_active_commit_veto_does_not_double_count_exposure():
    from tests.test_b2_hook_jump_guard import prepared,at_hook,ORIGIN,B
    n=prepared();n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B['J'],flags=0,received_frame=ORIGIN);n.sent()
    assert at_hook(n)==0
    assert len(n._failure_exposures)==1
    n.sent()
    assert len(n._failure_exposures)==1


def test_first_one_hp_after_veto_neutral_send_stops_learning(tmp_path):
    from tests.test_b2_hook_jump_guard import prepared,actual,ORIGIN,B
    from ssbot.combat.knife_chain_budget import LearningBudget,LearningStop
    n=prepared();budget=LearningBudget(tmp_path/'budget.json',batch='veto-neutral',revision='r',worker='i0');n.budget=budget
    base=actual(ORIGIN);n.observe_learning(base)
    n.before_send(frame=ORIGIN,target=ORIGIN+2,mask=B['J'],flags=0,received_frame=ORIGIN+2);n.sent()
    loss=actual(ORIGIN+3,target=ORIGIN+2,desired=0);loss['hero']['health']=base['hero']['health']-1
    with pytest.raises(LearningStop):n.observe_learning(loss)
    event=next(x for x in n.events if x['event']=='b2_hp_loss')
    assert event['chain_related'] and event['phase']=='recovery_after_failure'
    assert budget.state['b_fight_hp']==1 and budget.state['stop'] is not None


def test_wait_uses_stable_held_input_in_model_and_emitted_program(monkeypatch):
    owner,sim,ctx,seen=delayed_model(monkeypatch)
    p=owner.plan(sim,ctx,True,True,hop_from=1004,hop_wait_mask=cs.M_L,p_min=1007,first_feasible=True)
    assert p is not None and p.wait_mask==cs.M_L
    assert all(list(row[:2])==[cs.M_L,cs.M_L] for row in seen[0])
    assert cs.plan_mask(p,1002,1)==cs.plan_mask(p,1003,1)==cs.M_L
    assert cs.plan_mask(p,1004,1)==cs.M_J
    assert p.row()[-1]=={'wait_mask':cs.M_L}


def test_wait_mask_is_preserved_by_plan_adopt(monkeypatch):
    from ssbot.combat.knife_chain_slam import pl_adopt
    owner,sim,ctx,_=delayed_model(monkeypatch)
    p=owner.plan(sim,ctx,True,True,hop_from=1004,hop_wait_mask=cs.M_L,p_min=1007)
    q=cs.CsPlan(1003,0,1007,7);x=NS(v={},tmp={})
    pl_adopt(x,'var.tmp.adopted',q,p)
    assert (q.f0,q.hop,q.wait_mask)==(1004,3,cs.M_L)


@pytest.mark.parametrize('bad',[True,-1,1.5,'L',1<<64])
def test_bad_wait_mask_rejects_instead_of_inventing_keys(monkeypatch,bad):
    owner,sim,ctx=search(monkeypatch)
    with pytest.raises(ValueError,match='wait mask'):
        owner.plan(sim,ctx,True,True,hop_from=1004,hop_wait_mask=bad)


def test_held_jump_cannot_be_a_future_new_takeoff(monkeypatch):
    owner,sim,ctx=search(monkeypatch)
    assert owner.plan(sim,ctx,True,True,hop_from=1004,hop_wait_mask=cs.M_J) is None


def test_adapter_uses_observed_unchanging_wait_not_neutral(monkeypatch):
    kw=adapter(monkeypatch)
    assert kw['hop_wait_mask']==cs.M_L


@pytest.mark.parametrize('prefix,desired',[((),cs.M_L),((cs.M_R,),cs.M_L),((cs.M_J,),cs.M_J),((0,),None)])
def test_unknown_or_changing_wait_input_does_not_create_a_delayed_hop(monkeypatch,prefix,desired):
    assert adapter(monkeypatch,prefix=prefix,desired=desired) is None
