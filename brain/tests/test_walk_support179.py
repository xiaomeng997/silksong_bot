"""Task 179 (#296, the person 11-05: stomp the walking one): the explicit constant-velocity Walk support domain.

One future body set serves the press-now row: the hit core is its intersection, the target-body margin its union.
The domain ends a frame before the earliest Walk exit and at a hero path that could turn her (root crossed,
DistanceWalk band left). A walker facing away, a stopped / other-speed / unknown-clock Walk or an off-fit pose has
no domain. Live w13_pose178 786766c3 rows (walker 335470, 2519-2533) check the witness inside the actual colliders.
"""
import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K
from ssbot.combat import knife_chain_transfer as T,pogo_model as PM
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_eval import Run,X
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.map2 import clapper as cm
from tests.test_knife_chain_b2 import params,terrain
from tests.test_transfer_pose_witness178 import live_sim,LIVE

KNOW=cm.Know.load()
ROWS=len(LIVE['prefix'])+3+PM.ACTIVE[1]
EXIT_K=min(cm.WALK_FAR_MIN,cm.CLOSE_K[0])-1
# live 786766c3: walker 335470 walking toward the hero (flipX False, vel -8): frame, Control t, root x, body box
LIVE786=[(2519,.0,42.03,(39.985,3.015,43.371,6.195)),(2520,.0167,41.87,(39.825,3.015,43.211,6.195)),
         (2521,.0333,41.71,(39.665,3.015,43.051,6.195)),(2522,.05,41.55,(39.505,3.015,42.891,6.195)),
         (2523,.0666,41.39,(39.345,3.015,42.731,6.195)),(2524,.0833,41.39,(39.138,3.015,42.731,6.917)),
         (2525,.0999,41.23,(38.978,3.015,42.571,6.917)),(2526,.1165,41.07,(38.818,3.015,42.411,6.917)),
         (2527,.1332,40.91,(38.658,3.015,42.251,6.917)),(2528,.1499,40.75,(38.498,3.015,42.091,6.917)),
         (2529,.1665,40.59,(38.338,3.015,41.931,6.917)),(2530,.1832,40.59,(38.338,3.015,41.931,6.917)),
         (2531,.1998,40.43,(38.178,3.015,41.771,6.917)),(2532,.2165,40.27,(38.018,3.015,41.611,6.917)),
         (2533,.2331,40.11,(37.858,3.015,41.451,6.917))]
HERO786=[23.157,23.219,23.282,23.344,23.407,23.469,23.532,23.594,23.539,23.402,23.265,23.127,22.99,22.853,22.715]


def walker(t=0.,x=21.,flip=False,vx=8.,state='Walk',vy=0.,box=None):
 """Production-shaped walking target: Control clock, root, facing, velocity and the collider of its fitted pose."""
 b=KNOW.box('Walk',int(round(t*60)));face=1 if flip else -1;y=cm.FLOOR-float(b[2])
 xa,xb=x+face*b[0],x+face*b[1]
 x0,y0,x1,y1=box if box is not None else (min(xa,xb),y+b[2],max(xa,xb),y+b[3])
 return {'iid':1,'pos':[x,y,0.],'vel':[vx,vy],'flipX':flip,'fsms':[{'name':'Control','state':state,'t':t}],
  'colliders':[{'name':'Song Heavy Sentry (2)','enabled':True,'layer':11,'verts_world':[x0,y0,x1,y0,x1,y1,x0,y1]}]}


@pytest.mark.parametrize('k',[0,3,EXIT_K-1])
def test_domain_ends_a_frame_before_the_earliest_walk_exit(k):
 s=T.walk_body_support(walker(t=k/60.,x=30.,vx=-8.),20,{'pos':[22.,4.6]})
 assert s.info['domain_frames']==EXIT_K-k and s.info['walk_dir']==1 and s.info['toward']==-1
 core,hull=s(np.full(20,22.))
 n=EXIT_K-k
 assert np.isfinite(hull[:n]).all() and np.isfinite(core[:n]).all()
 assert np.isnan(hull[n:]).all() and np.isnan(core[n:]).all()
 assert T.walk_body_support(walker(t=EXIT_K/60.,x=30.,vx=-8.),20,{'pos':[22.,4.6]}) is None


def test_core_is_the_intersection_and_hull_the_union_of_one_body_set():
 k=3;x=30.;s=T.walk_body_support(walker(t=k/60.,x=x,vx=-8.),20,{'pos':[22.,4.6]})
 core,hull=s(np.full(20,22.))
 r=(1/60.)/cm.DT;step=-8.*cm.DT

 def boxes(d):
  lo,hi=(0,0) if d==0 else (int(np.floor((d-1)*r)),int(np.ceil((d+1)*r)))
  out=[]
  for q in range(k+d-3,k+d+2):
   b=KNOW.box('Walk',max(q,0))
   for m in range(lo,hi+1):  # every step count, not only the extremes the support samples
    xa,xb=x+step*m-b[0],x+step*m-b[1]
    out.append((min(xa,xb),cm.FLOOR,max(xa,xb),cm.FLOOR+b[3]-b[2]))
  return np.array(out)

 for d in range(s.info['domain_frames']):
  both=np.vstack([boxes(d),boxes(d-1) if d else boxes(d)])
  assert np.allclose(core[d],[both[:,0].max(),both[:,1].max(),both[:,2].min(),both[:,3].min()])
  assert np.allclose(hull[d],[both[:,0].min(),both[:,1].min(),both[:,2].max(),both[:,3].max()])
 n=s.info['domain_frames']
 assert (core[:n,0]>=hull[:n,0]).all() and (core[:n,2]<=hull[:n,2]).all() and (core[:n,3]<=hull[:n,3]).all()


def test_live_786_walk_witness_stays_inside_the_actual_colliders_of_both_damage_frames():
 f0,t0,x0,box0=LIVE786[0]
 s=T.walk_body_support(walker(t=t0,x=x0,vx=-8.,box=box0),len(LIVE786),{'pos':[HERO786[0],4.6]})
 assert s.info['domain_frames']==EXIT_K and s.info['walk_dir']==1  # forward toward her, 18.9 u away
 core,hull=s(np.array(HERO786))
 for d in range(1,EXIT_K):
  now,before=np.array(LIVE786[d][3]),np.array(LIVE786[d-1][3])
  for b in (now,before):  # damage reads the previous frame's colliders: the witness is inside both
   assert core[d][0]>=b[0]-T.POSE_MATCH_U and core[d][2]<=b[2]+T.POSE_MATCH_U and core[d][3]<=b[3]+T.POSE_MATCH_U
   assert hull[d][0]<=b[0]+T.POSE_MATCH_U and hull[d][2]>=b[2]-T.POSE_MATCH_U and hull[d][3]>=b[3]-T.POSE_MATCH_U
 assert np.isnan(core[EXIT_K:]).all() and np.isnan(hull[EXIT_K:]).all()


def test_hero_paths_that_could_turn_her_end_the_domain():
 # backing away (Walk B): she walks right at 8 u/s, the hero 1.5 u to her left
 s=T.walk_body_support(walker(t=0.,x=21.,flip=False,vx=8.),20,{'pos':[19.5,8.]})
 assert s.info['walk_dir']==-1 and s.info['domain_frames']==EXIT_K
 still,_=s(np.full(20,19.5))
 assert np.isfinite(still[:EXIT_K]).all()
 crossing,crossing_hull=s(19.5+.5*np.arange(20))  # she is overtaken: FaceObjectV2 / DistanceWalk's side flips
 first=int(np.argmax(np.isnan(crossing_hull[:,0])))
 assert 1<=first<6 and np.isnan(crossing[first:]).all() and np.isfinite(crossing_hull[:first]).all()
 leaving,_=s(19.5-.6*np.arange(20))  # past 8.5 u DistanceWalk walks forward again
 end=int(np.argmax(np.isnan(leaving[:,0])))
 assert 5<=end<11 and np.isnan(leaving[end:]).all()
 # walking toward her: entering 5.5 u turns her back, so a hero already inside has no domain at all
 assert T.walk_body_support(walker(t=0.,x=26.,vx=-8.),20,{'pos':[21.,8.]}) is None


@pytest.mark.parametrize('case',['idle','stopped','slow','vertical','no_clock','nan_clock','negative_clock',
                                 'facing_away','off_fit','off_floor','no_hero'])
def test_no_constant_velocity_walk_no_domain(case):
 kw=dict(t=0.,x=21.,flip=False,vx=8.);hero={'pos':[19.5,8.]}
 if case=='idle':kw['state']='Idle'
 if case=='stopped':kw['vx']=0.
 if case=='slow':kw['vx']=7.9
 if case=='vertical':kw['vy']=.5
 if case=='facing_away':kw['flip']=True
 e=walker(**kw)
 if case=='no_clock':e['fsms'][0]['t']=None
 if case=='nan_clock':e['fsms'][0]['t']=float('nan')
 if case=='negative_clock':e['fsms'][0]['t']=-.1
 if case=='off_fit':e['colliders'][0]['verts_world'][::2]=[v+.1 for v in e['colliders'][0]['verts_world'][::2]]
 if case=='off_floor':e['colliders'][0]['verts_world'][1::2]=[v+.1 for v in e['colliders'][0]['verts_world'][1::2]]
 if case=='no_hero':hero={}
 assert T.walk_body_support(e,20,hero) is None


def test_live_input_walking_row_hits_the_core_and_margins_the_hull_of_the_same_set(params,terrain,monkeypatch):
 sim=live_sim(params,terrain,4)  # the logged 2735 state rolled four frames with no keys: a model hero
 e=walker(t=0.,x=21.,flip=False,vx=8.)
 hero={'pos':[float(np.asarray(sim.start).reshape(K.K,-1)[K.PX,0]),float(np.asarray(sim.start).reshape(K.K,-1)[K.PY,0])]}
 s=T.walk_body_support(e,ROWS,hero)
 assert s is not None and s.info['walk_dir']==-1
 grazed=[]
 real=T.grazes_body
 monkeypatch.setattr(T,'grazes_body',lambda boxes,body,until:grazed.append(np.array(body)) or real(boxes,body,until))
 row=T.press_now_row(sim,s,2741,0,0)
 assert row is not None and row['support']=='walk' and row['walk']['vx']==8. and row['walk']['walk_dir']==-1
 assert 0<row['contact_frame']-sim.fo<s.info['domain_frames'] and 'steps' not in row['walk']
 assert grazed  # a moving body is always margin-checked, attacking or not
 ro=sim.roll(np.asarray([row['masks']],np.int64))
 assert np.array_equal(grazed[-1],s(ro.pos[0,:,0])[1],equal_nan=True)  # the hull of this row's own path
 monkeypatch.setattr(T,'grazes_body',lambda *a:True)
 assert T.press_now_row(sim,s,2741,0,0) is None  # the core alone never licenses a row


def test_walk_supported_strike_reselects_when_she_leaves_the_constant_walk_before_contact():
 r=load_runner();row={'support':'walk','contact_frame':1010,'walk':{'vx':8.,'flip':False},'press_F':1006}
 r.run=Run(T.PROGRAM,'strike',{'row':row,'side':B['R']})
 guard=r.P.guards['transfer_walk_support_lost']
 def at(f,**kw):
  return X(r,r.run,NS(f=f,e=walker(**{'t':.1,'x':21.,'flip':False,'vx':8.,**kw})))
 assert not guard(at(1005))
 assert guard(at(1005,state='Idle')) and guard(at(1005,vx=-8.)) and guard(at(1005,vx=0.))
 assert guard(at(1005,flip=True))
 assert not guard(at(1010,state='Idle'))  # at / after the contact the strike resolves by bounce or miss
 r.run.v['row']={**row,'support':None}
 assert not guard(at(1005,state='Idle'))
 table=json.loads(Path(T.__file__).with_name('knife_chain_air_v01.json').read_text(encoding='utf-8'))
 rules=table['rune_transfer']['links']['strike']['rules']
 assert {'do':'abort','when':{'p':'transfer_walk_support_lost'}}.items()<=rules[1].items()


def test_stomp_plan_walk_branch_uses_the_walk_domain_never_the_still_witness(monkeypatch):
 r=load_runner();r.run=Run(T.PROGRAM,'air',{'jump_until':0,'side':B['L']})
 hero={'pos':[19.5,8.]}
 x=X(r,r.run,NS(sim=NS(prefix=[0]),e=walker(t=0.,x=21.,flip=False,vx=8.),F=1002,k=2,ground=False,hero=hero))
 monkeypatch.setattr(T,'contact_body_witness',lambda *a,**kw:pytest.fail('still witness on a walking body'))
 seen=[]
 monkeypatch.setattr(T,'press_now_row',lambda sim,body,*a,**kw:seen.append(body) or {'press_F':1003,'support':'walk'})
 assert r.P.acts['transfer_stomp_plan'](x)=={'do':'goto','to':'strike'}
 assert isinstance(seen[0],T.WalkSupport) and r.run.v['row']['support']=='walk'
 r.run=Run(T.PROGRAM,'air',{'jump_until':0,'side':B['L']});seen.clear()
 x=X(r,r.run,NS(sim=NS(prefix=[0]),e=walker(t=EXIT_K/60.,x=21.,flip=False,vx=8.),F=1002,k=2,ground=False,hero=hero))
 assert r.P.acts['transfer_stomp_plan'](x) is None and not seen and 'row' not in r.run.v


def test_fresh_walking_stomp_goes_through_the_native_offer_install_before_send_and_send(monkeypatch):
 """Component positive example on the production chain path (HERO2 airborne hero, production-shaped STATE):
 transfer.propose -> stomp_plan -> WalkSupport -> press_now_row -> B2 offer -> install / before_send / sent.
 The external geometry is stubbed clear; the Sol demo archive has no real frame in this domain near an
 airborne hero with an L2 stomp request (opus/review179/c_walk s52 / s53)."""
 from ssbot.combat import knife_chain_air_native as N
 from tests.test_shared_strike_approach import flight
 from tests.test_knife_chain_transfer import fit_pose
 from tests.test_target_entry_attack import native
 r,s,sim=flight(x=20.,y=9.,vx=8.,vy=0.,target_x=21.5);r.run=None
 e=s['ents'][1];e['vel']=[8.,0.];e['flipX']=False;fit_pose(e,'Walk',0.,21.5)  # backing away from her at 8 u/s
 class Clear:
  def __init__(self,*a):pass
  def scan(self,path):return NS(complete=True,contacts=())
  preflight=scan
 monkeypatch.setattr(N,'B2Geometry',Clear)
 n=native();n.runner=r;n._transfer_ready=True;n._context=(None,None,None,np.zeros((0,6)))
 n._transfer_goal=T.TransferGoal(8,7,990,0.)
 monkeypatch.setattr(n,'queued_prefix',lambda *a:(0,'known test prefix'))
 offer=n._transfer_offer(s,0.,sim,NS(rs=NS(trk=NS(now={8:(None,None,None)}))),NS(target=8),False)
 assert offer.stage=='manual_commitment' and offer.details['phase']=='strike'
 assert offer.details['strike_support']=='walk' and offer.details['strike_walk']['walk_dir']==-1
 row=offer.draft.run.v['row']
 assert row['support']=='walk' and 0<row['contact_frame']-sim.f<row['walk']['domain_frames']
 n.dispatch.begin_tick(sim.f)
 res=n.install(offer,NS(measurement_enabled=False));n.planner_result(res);n.final('plan',offer.mask)
 n.before_send(frame=sim.f,target=sim.f+2,mask=offer.mask,flags=0,received_frame=sim.f)
 assert n.sent().chain_outcome=='sent'
 assert n.runner.run.link=='strike' and n.runner.run.v['row']['support']=='walk' and n.commitment is not None
