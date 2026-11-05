"""Fresh stationary-body witnesses cannot certify a moving destination."""
from types import SimpleNamespace as NS
import pytest
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_eval import Run,X
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_commitment import MoveInstance


@pytest.mark.parametrize('state,vel',[
 ('Evade Scuttle',[-15.,0.]),('Walk',[0.,0.]),('Evade Scuttle',[0.,0.]),
 ('Idle',[.01,0.]),('Idle',None),('Idle',[]),('Idle',[float('nan'),0.]),
 ('Idle',[False,0.]),('Idle',['0',0.]),('Idle',[0.,float('inf')]),
])
def test_fresh_moving_or_unknown_body_does_not_even_roll_a_strike(monkeypatch,state,vel):
 r=load_runner();r.run=Run(T.PROGRAM,'air',{'jump_until':0,'side':B['R']})
 e={'vel':vel,'fsms':[{'name':'Control','state':state,'t':0.}]}
 x=X(r,r.run,NS(sim=object(),e=e,F=1002,k=2,ground=False))
 calls=[]
 monkeypatch.setattr(T,'body_box',lambda e:[0.,0.,1.,1.])
 monkeypatch.setattr(T,'press_now_row',lambda *a:calls.append(a) or {'press_F':1003})
 assert r.P.acts['transfer_stomp_plan'](x) is None
 assert not calls and 'row' not in r.run.v
 assert r.run.link=='air'  # keep the existing drift/approach, not a recovery


@pytest.mark.parametrize('state',['Idle','Spell Antic','Slam Antic','Slam Recover'])
def test_known_stationary_target_keeps_existing_three_row_witness(monkeypatch,state):
 r=load_runner();r.run=Run(T.PROGRAM,'air',{'jump_until':0,'side':B['R']})
 e={'vel':[0.,0.],'fsms':[{'name':'Control','state':state,'t':0.}]}
 x=X(r,r.run,NS(sim=NS(prefix=[0]),e=e,F=1002,k=2,ground=False));row={'press_F':1003}
 monkeypatch.setattr(T,'contact_body_witness',lambda e,n,**kw:[[0.,0.,1.,1.]]*n)  # Task 178: the pose witness
 monkeypatch.setattr(T,'press_now_row',lambda *a,**kw:row)
 assert r.P.acts['transfer_stomp_plan'](x)=={'do':'goto','to':'strike'}
 assert r.run.v['row'] is row


def exposure_fixture(sent=True,bound=True):
 from ssbot.combat.knife_chain_air_native import NativeManualAirChain
 n=NativeManualAirChain(runner_factory=load_runner,probe_ref='transfer239');n.reset(0,start_frame=1000)
 m=MoveInstance(8,1000,'RUNE_TRANSFER');cast=MoveInstance(7,990,'CC_CAST');slam=MoveInstance(8,1039,'CC_SLAM')
 n.commitment={'move':m,'origin':1000,'ta':0.}
 n._transfer_responsibility[m]=(cast,0.)
 if bound:n._transfer_target_moves[m]=(slam,.65)
 n._press=1037 if sent else None
 n._actual_state={'f':1050,'ents':[{'iid':7,'hp':100,'fsms':[{'name':'Control','state':'Idle','t':0.}]},
   {'iid':8,'hp':100,'fsms':[{'name':'Control','state':'Slam Antic','t':11/60}]}]}
 n._clock=50/60
 return n,m,cast,slam


def test_sent_miss_keeps_both_source_and_bound_destination_liability_without_banning_new_slam():
 n,m,cast,slam=exposure_fixture()
 n._recover('transfer downslash missed; no observed target bounce',1050)
 assert {e.move for e in n._failure_exposures}=={cast,slam}
 exposure=next(e for e in n._failure_exposures if e.move==slam)
 assert exposure.origin==1039 and exposure.active(1094) and exposure.through is None
 assert slam not in n._failed_hook_moves and m in n._failed_hook_moves
 assert n.commitment is None and n.runner.run is None
 n._recover('again with no commitment',1051)
 assert len(n._failure_exposures)==2


@pytest.mark.parametrize('sent,bound',[(False,True),(True,False),(False,False)])
def test_unsent_or_unbound_destination_never_invents_an_extra_exposure(sent,bound):
 n,m,cast,slam=exposure_fixture(sent,bound)
 n._recover('failed',1050)
 assert [e.move for e in n._failure_exposures]==[cast]


def test_actual_expiry_retains_table_reason_in_propose_result():
 import numpy as np
 from tests.test_knife_chain_transfer import transfer_at_gap
 r,s,sim=transfer_at_gap(5.)
 r.run.link='strike';r.run.v['row']={'F0':990,'press_F':980,'contact_frame':986,'masks':[0]}
 made=T.propose(r,s,0.,sim,8,True,np.zeros((0,6)),set())
 assert made[0] is None
 assert made[1].ended_reason=='transfer downslash missed; no observed target bounce'
