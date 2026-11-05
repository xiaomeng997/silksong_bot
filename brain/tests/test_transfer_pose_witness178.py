"""Task 178: the downslash contact witness follows the target's fitted pose.

Live w13_face_hook e4a2318b: 2735 pressed (2738) against the Cast 2 body held at its decision height. Cast 2
crouches 1.56 u at k15 (2741), no hit came in the window, and the hero fell into the Idle body (-2 HP at 2755).
"""
import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K
from ssbot.combat import knife_chain_transfer as T,pogo_model as PM
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_air import body_box,load_runner
from ssbot.combat.knife_chain_eval import Run,X
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.map2 import clapper as cm
from tests.test_knife_chain_b2 import params,terrain

LIVE=json.loads((Path(__file__).resolve().parent/'data'/'transfer178_live2735.json').read_text(encoding='utf-8'))
KNOW=cm.Know.load()
HIGH=cm.FLOOR+.309+4.452;LOW=cm.FLOOR-1.255+4.434  # fitted Cast high and crouched tops, standing on the floor
ROWS=len(LIVE['prefix'])+3+PM.ACTIVE[1]


def target(f):return json.loads(json.dumps(LIVE['target'][str(f)]))


def clapper(state,t,x=19.5634,flip=True,vel=(0.,0.)):
 """Production-shaped target: Control clock, root, facing and the body collider of its fitted pose."""
 b=KNOW.box(state,int(round(t*60)));face=1 if flip else -1;y=cm.FLOOR-float(b[2])
 xa,xb=x+face*b[0],x+face*b[1];x0,y0,x1,y1=min(xa,xb),y+b[2],max(xa,xb),y+b[3]
 return {'iid':1,'pos':[x,y,0.],'vel':list(vel),'flipX':flip,'fsms':[{'name':'Control','state':state,'t':t}],
  'colliders':[{'name':'Song Heavy Sentry (2)','enabled':True,'layer':11,'verts_world':[x0,y0,x1,y0,x1,y1,x0,y1]}]}


def live_sim(params,terrain,s=0):
 """The logged production input of 2735; s > 0 rolls the air link's own keys (0) s frames: a model hero."""
 h=LIVE['hold'];S=np.asarray(LIVE['hero_state'],float);pre=np.asarray(LIVE['prefix'],np.int64)
 H=K.HoldState(np.asarray(h['latched'],bool),np.asarray(h['desired'],bool),np.asarray(h['pending'],int),
  np.minimum(np.asarray(h['age'],int)+s,255))
 if s:
  S=ChainSim(S,pre,H,params,terrain,2735,2735).roll(np.zeros((1,s-1),np.int64)).final.reshape(K.K,1)
  pre=np.zeros(1,np.int64)
 return ChainSim(S,pre,H,params,terrain,2735+s,2735+s)


def test_live_cast2_witness_crouches_at_its_fitted_frame_inside_the_actual_colliders():
 e=target(2735);w=T.contact_body_witness(e,ROWS)
 assert e['fsms'][0]['state']=='Cast 2' and round(e['fsms'][0]['t']*60)==9
 assert np.allclose(w[:5,3],HIGH,atol=.002) and np.allclose(w[5:,3],LOW,atol=.002)
 for d in range(ROWS):
  for g in (2735+d,2734+d):
   if str(g) in LIVE['target']:
    b=body_box(target(g))
    assert w[d][0]>=b[0]-T.POSE_MATCH_U and w[d][2]<=b[2]+T.POSE_MATCH_U and w[d][3]<=b[3]+T.POSE_MATCH_U


def test_live_2735_waits_for_the_crouched_body_and_strikes_it_inside_the_window(params,terrain,monkeypatch):
 sim=live_sim(params,terrain);e=target(2735)
 monkeypatch.setattr(T,'CONTACT_END_MARGIN_F',0)
 old=T.press_now_row(sim,body_box(e),2737,0,0)  # a3bb4a68: the decision-time body held still
 assert (old['press_F'],old['contact_frame'])==(2738,2747)  # the live press; no hit, missed at 2751
 assert T.press_now_row(sim,T.contact_body_witness(e,ROWS),2737,0,0) is None
 monkeypatch.setattr(T,'CONTACT_END_MARGIN_F',1)
 for s in range(1,5):  # model hero, recorded target: wait through 2739
  assert T.press_now_row(live_sim(params,terrain,s),T.contact_body_witness(target(2735+s),ROWS),2737+s,0,0) is None
 row=T.press_now_row(live_sim(params,terrain,5),T.contact_body_witness(target(2740),ROWS),2742,0,0)
 assert (row['press_F'],row['contact_frame'])==(2743,2751)


def test_a_contact_only_on_the_last_active_frame_waits_a_tick(params,terrain,monkeypatch):
 sim=live_sim(params,terrain,4);w=T.contact_body_witness(target(2739),ROWS)
 monkeypatch.setattr(T,'CONTACT_END_MARGIN_F',0)
 row=T.press_now_row(sim,w,2741,0,0)
 assert (row['press_F'],row['contact_frame'])==(2742,2751) and row['contact_frame']-row['press_F']==PM.ACTIVE[1]
 monkeypatch.setattr(T,'CONTACT_END_MARGIN_F',1)
 assert T.press_now_row(sim,w,2741,0,0) is None


def test_press_now_row_takes_one_box_per_step_and_skips_unwitnessed_steps(params,terrain):
 sim=live_sim(params,terrain,5);w=T.contact_body_witness(target(2740),ROWS)
 assert T.press_now_row(sim,w,2742,0,0)['contact_frame']==2751
 blind=w.copy();blind[2751-2740]=np.nan
 assert T.press_now_row(sim,blind,2742,0,0) is None


def in_range(e):
 x,y=e['pos'][:2];return [x-.25,y+.5,x+.25,y+2.5]  # a hero box inside her Slam Range


@pytest.mark.parametrize('state,t',[('Spell Antic',22/60),('Idle',20/60),('Cast 1',2/60)])
def test_stable_poses_keep_the_held_observed_body(state,t):
 e=clapper(state,t);w=T.contact_body_witness(e,ROWS,idle_no_evade=True);b=body_box(e)
 assert np.allclose(w[:,[0,2,3]],[b[0],b[2],b[3]],atol=T.POSE_MATCH_U)


def test_idle_witness_ends_at_her_modelled_exits():
 # Live w13_pose178 2610: Idle k10, contact planned at k19; she evaded at k17 (15 u/s) and the slash missed.
 w=T.contact_body_witness(clapper('Idle',10/60),ROWS)
 assert np.isfinite(w[:5]).all() and np.isnan(w[5:]).all()  # Can Evade (k15) on: Will Evade unknown
 assert np.isnan(T.contact_body_witness(clapper('Idle',18/60),ROWS)).all()  # past Can Evade, still open
 assert np.isfinite(T.contact_body_witness(clapper('Idle',18/60),ROWS,idle_no_evade=True)).all()
 w=T.contact_body_witness(clapper('Idle',35/60),ROWS,idle_no_evade=True)
 assert np.isfinite(w[:4]).all() and np.isnan(w[4:]).all()  # Idle Time (k39) on: she walks
 e=clapper('Idle',18/60);x,y=e['pos'][:2]
 assert T.in_slam_range(e,in_range(e)) and not T.in_slam_range(e,[x+20,y,x+20.5,y+2]) and not T.in_slam_range(e,None)


def test_stomp_plan_shows_will_evade_false_only_after_an_in_range_frame_plus_lag(monkeypatch):
 r=load_runner();r.run=Run(T.PROGRAM,'air',{'jump_until':0,'side':B['R']});seen=[]
 monkeypatch.setattr(T,'contact_body_witness',lambda e,n,**kw:seen.append(kw['idle_no_evade']))
 for f,k,box in ((1000,15,True),(1001,16,True),(1002,17,True),(1003,18,True),(1004,19,False)):
  e=clapper('Idle',k/60);hero={'box':in_range(e) if box else None}
  r.P.acts['transfer_stomp_plan'](X(r,r.run,NS(sim=NS(prefix=[0]),e=e,f=f,F=f+2,k=2,ground=False,hero=hero)))
 assert seen==[False,False,False,True,True]  # first in range at k16 (k15 is before EV_K[1]); +2 frames: k18


def test_a_hooked_run_keeps_the_provoked_attack_liability_without_a_downslash():
 from ssbot.combat.claw_strike import CsPlan
 from tests.test_transfer_motion239 import exposure_fixture
 n,m,cast,slam=exposure_fixture(sent=False)
 n.runner.run=Run(T.PROGRAM,'air',{'cs':CsPlan(1000,0,1001,0,bb_press=None),'hook_hit_f':1012})
 n._recover('transfer face hook released into the target\'s attack or unknown state',1050)
 assert {e.move for e in n._failure_exposures}=={cast,slam}


@pytest.mark.parametrize('field,value',[
 ('flipX',None),('flipX',1),('vel',[.5,0.]),('vel',[0.,-.1]),('vel',None),
 ('t',float('nan')),('t',-1.),('state','Dmg Attack'),('state','Walk'),('state','Slam 0'),('state',None)])
def test_unknown_or_moving_pose_has_no_witness(field,value):
 e=clapper('Cast 2',9/60)
 if field in ('t','state'):e['fsms'][0][field]=value
 else:e[field]=value
 assert T.contact_body_witness(e,ROWS) is None


def test_a_collider_that_does_not_match_its_clock_or_facing_has_no_witness():
 late=clapper('Cast 2',24/60);late['colliders']=clapper('Cast 2',9/60)['colliders']  # clock crouched, collider high
 turned=clapper('Spell Antic',22/60,flip=False);turned['colliders']=clapper('Spell Antic',22/60)['colliders']
 assert T.contact_body_witness(late,ROWS) is None and T.contact_body_witness(turned,ROWS) is None


def test_slam_antic_witness_stops_where_the_lunge_can_start():
 w=T.contact_body_witness(clapper('Slam Antic',45/60),ROWS)
 assert np.isfinite(w[:2]).all() and np.isnan(w[2:]).all()


@pytest.mark.parametrize('t,known',[(1.,False),(26/60,False),(25/60,True)])
def test_a_timed_clock_past_its_supported_duration_is_unknown_not_its_successor(t,known):
 # Astra 178-R1: the live 2744 Cast 2 (supported 24..26 frames) with only its clock moved.
 e=target(2744);e['fsms'][0]['t']=t
 assert (T.contact_body_witness(e,ROWS) is not None)==known
 assert T.contact_body_witness(clapper("Idle",30.),ROWS) is not None  # Idle has no clock bound; its exits do (rows)


def test_a_body_that_does_not_stand_on_the_floor_is_unknown():
 lifted=clapper('Cast 2',9/60);lifted['pos'][1]+=2.
 v=lifted['colliders'][0]['verts_world'];v[1::2]=[y+2. for y in v[1::2]]
 assert T.contact_body_witness(lifted,ROWS) is None and T.contact_body_witness(clapper('Cast 2',9/60),ROWS) is not None


def test_stomp_plan_rolls_the_rows_against_the_pose_witness_and_waits_without_one(monkeypatch):
 r=load_runner();r.run=Run(T.PROGRAM,'air',{'jump_until':0,'side':B['R']})
 e={'vel':[0.,0.],'fsms':[{'name':'Control','state':'Cast 2','t':.15}]}
 x=X(r,r.run,NS(sim=NS(prefix=np.zeros(1,np.int64)),e=e,F=1002,k=2,ground=False))
 witness=np.zeros((ROWS,4));seen=[];row={'press_F':1003}
 monkeypatch.setattr(T,'contact_body_witness',lambda e,n,**kw:seen.append(n) or witness)
 monkeypatch.setattr(T,'press_now_row',lambda sim,body,*a:seen.append(body) or row)
 assert r.P.acts['transfer_stomp_plan'](x)=={'do':'goto','to':'strike'}
 assert seen[0]==ROWS and seen[1] is witness and r.run.v['row'] is row
 r.run=Run(T.PROGRAM,'air',{'jump_until':0,'side':B['R']});x=X(r,r.run,x.obs);seen.clear()
 monkeypatch.setattr(T,'contact_body_witness',lambda e,n,**kw:None)
 assert r.P.acts['transfer_stomp_plan'](x) is None
 assert not seen and 'row' not in r.run.v and r.run.link=='air'  # keep the existing drift/approach, not a recovery
