"""Task 179 (#296, the person 11-05: when the corner one jumps, go over the walking one, never the corner).

The vault's ground approach runs into its ONE manual distance table (near jump / small-hop hook; the person 11-02:
by distance, no whole-skill pre-validation), its entry tick keeps the first ground-jump slot, and inside the vault's
own domain the vault goes before the SWITCH stomp. Live w13_pose178 786766c3 2580: the walker 11.7 u away was past
the hook's 9.5 u, no table action existed, and the planner took the corner under the landing.
"""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import knife_chain_vault as V,knife_chain_vault_native as VN
from ssbot.combat.knife_chain_vault_native import manual_entries
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from tests import test_knife_chain_vault_manual as M

CFG=V.load_vault_runner()[0].chains[V.CHAIN].cfg
BOMBS=np.zeros((0,6))


@pytest.mark.parametrize('root,harpoon,silk,kind',[(5.,True,9,'near'),(5.,False,0,'near'),(7.,True,9,'hop_hook'),
                                                    (9.5,True,9,'hop_hook'),(9.6,True,9,None),(7.,False,9,None),
                                                    (7.,True,0,None)])
def test_one_distance_table_names_the_near_jump_the_hook_or_nothing(root,harpoon,silk,kind):
 hb=[19.75,3.015,20.25,5.094];x=20.+root;box=[x-2.252,3.015,x+1.341,6.917]  # the Walk / Idle body facing her
 hero={'box':hb,'pos':[20.,4.5],'can':{'harpoon':harpoon},'silk':silk,'tm':{'atk_cd':0.}}
 got,part,gap,distance=V.distance_entry(CFG,hero,[x,7.449],box,1,.25)
 assert got==kind and distance==pytest.approx(root) and gap==pytest.approx(box[0]-hb[2])
 if kind=='near':assert part=={'h':14,'p':8,'before':'T'}
 if kind=='hop_hook':assert part=={k:CFG['HOP_RECIPE'][k] for k in ('hop','claw_after','d','p')}
 hero['tm']['atk_cd']=.2  # the current swing's cooldown moves the press inside the same row, never declines it
 assert kind!='near' or V.distance_entry(CFG,hero,[x,7.449],box,1,.25)[1]['p']==11


@pytest.mark.parametrize('direction',[-1,1])
def test_approach_runs_toward_the_target_then_names_the_hook_from_the_same_table(direction):
 n,raw,sim,ctx=M.entry_scene(direction,12.)
 (kind,req),=manual_entries(n,raw,sim,ctx)
 assert kind=='approach' and req['approach']=={k:CFG['APPROACH'][k] for k in ('max_f','startup_f','absolute_f')}
 assert (CFG['APPROACH']['max_f'],CFG['APPROACH']['startup_f'],CFG['APPROACH']['absolute_f'])==(24,4,28)
 assert req['near'] is None and req['far'] is None and req['over_dir']==direction
 r=n.runner;r.anchor.open(req)
 m=r.step(sim.f,raw,True,True,t_game=10.,sim=sim,bombs=BOMBS)
 toward=B['R'] if direction>0 else B['L']
 assert r.run.link=='approach' and m==toward  # running keys only: no jump, hook, dash or swing
 _,closer,_,_=M.entry_scene(direction,7.)  # she ran, it walked: 7 u now
 closer['f']=raw['f']+1
 m=r.step(sim.f+1,closer,True,True,t_game=10.+1/60,sim=sim,bombs=BOMBS)
 assert r.run.link=='far' and r.run.v['cs'] is not None and m&B['J'] and not m&B['CLAW']
 assert r.run.v['req']['far']=={k:CFG['HOP_RECIPE'][k] for k in ('hop','claw_after','d','p')}


def test_approach_names_the_near_jump_when_the_hook_is_unavailable():
 n,raw,sim,ctx=M.entry_scene(-1,12.)
 (_,req),=manual_entries(n,raw,sim,ctx)
 r=n.runner;r.anchor.open(req);r.step(sim.f,raw,True,True,t_game=10.,sim=sim,bombs=BOMBS)
 _,closer,_,_=M.entry_scene(-1,4.2);closer['f']=raw['f']+1;closer['hero']['can']['harpoon']=False
 m=r.step(sim.f+1,closer,True,True,t_game=10.+1/60,sim=sim,bombs=BOMBS)
 assert r.run.link=='near' and r.run.v['row']['F0']==closer['f']+2 and m&B['J']


def held(raw,sim,key,desired=None,pending=0,nxt=None):
 """The STATE's HoldFilter has `key` latched (desired / its queued toggles as given) and the in-flight desired of the
 next frame is `nxt` (default the key): the copy of sim carries that prefix."""
 from dataclasses import replace
 bit=key.bit_length()-1 if key else 0
 hf=raw['act']['hf'];hf['latched']=key;hf['desired']=key if desired is None else desired
 hf['pending']=[0]*22;hf['pending'][bit]=pending
 return replace(sim,prefix=np.array([key if nxt is None else nxt],np.int64))


@pytest.mark.parametrize('case,closed,why',[('buddy_landed','abort',"jump is over"),
                                            ('airborne','abort','off the ground'),
                                            ('startup','abort','running not confirmed within its start-up frames'),
                                            ('timeout','abort','no table range within its frames'),
                                            ('absolute','abort','no table range within its absolute frames'),
                                            ('target_moved','done','left Idle / Walk')])
def test_approach_ends_with_an_explicit_reason(case,closed,why):
 n,raw,sim,ctx=M.entry_scene(-1,12.)
 (_,req),=manual_entries(n,raw,sim,ctx)
 if case=='absolute':req['approach']['max_f']=40  # only so that the absolute bound is the first to end it
 if case in ('timeout','absolute'):sim=held(raw,sim,B['L'])  # running confirmed at the admission
 r=n.runner;r.anchor.open(req);r.step(sim.f,raw,True,True,t_game=10.,sim=sim,bombs=BOMBS)
 assert r.run.v['run_f']==(sim.f if case in ('timeout','absolute') else None)
 a=CFG['APPROACH']
 f=sim.f+{'timeout':a['max_f']+1,'absolute':a['absolute_f']+1,'startup':a['startup_f']}.get(case,1);raw['f']=f
 if case=='buddy_landed':raw['ents'][1]['fsms'][0]['state']='Slam 2'
 if case=='target_moved':raw['ents'][0]['fsms'][0]['state']='Slam Antic'
 assert r.step(f,raw,case!='airborne',True,t_game=10.+(f-sim.f)/60,sim=sim,bombs=BOMBS) is None
 assert r.run is None and r.done[-1].closed==closed and why in r.done[-1].v['why']


def test_only_the_approach_entry_tick_arms_the_first_ground_jump_slot():
 move=MoveInstance(7,990,'VAULT_IDLE')
 approach=NS(draft=NS(run=NS(v={'cs':None,'row':None},link='approach')),move=move)
 assert VN.manual_jump_watch(approach,1000) is None  # running keys only: no ground jump to watch
 row={'F0':1002,'masks':[B['J'],B['J'],0]}
 def entry(flag):
  return NS(draft=NS(run=NS(v={'cs':None,'row':row},link='near')),move=move,mask=B['J'],stage='active',
            details={'distance_vault':True,'approach_entry':flag})
 native=NS(_jump_start=None,require_send_clock=False,_abort_hook_dispatch=lambda selected,**kw:kw['reason'])
 assert VN.before_send(native,entry(True),frame=1000,target=1002,mask=B['J'],flags=0,received_frame=1000,
                       dispatch_clock=None) is None
 assert VN.before_send(native,entry(True),frame=1000,target=1002,mask=B['J'],flags=0,received_frame=1002,
                       dispatch_clock=None)=='vault first ground-jump slot already missed'
 assert VN.before_send(native,entry(False),frame=1000,target=1002,mask=B['J'],flags=0,received_frame=1002,
                       dispatch_clock=None) is None  # an ordinary active tick has no fresh slot of its own


def test_vault_domain_takes_the_switch_stomp_when_its_table_has_an_action(monkeypatch):
 from tests.test_knife_chain_vault_nominal import TARGET
 original=M.entry_scene
 monkeypatch.setattr(M,'entry_scene',lambda direction,distance:original(direction,12.))
 n,raw,sim,prefs,delegated,marker=M._switch_routing_scene('left',monkeypatch)
 class SafeGeometry:
  def __init__(self,*a):pass
  def preflight(self,path):return NS(complete=True,contacts=())
  scan=preflight
 monkeypatch.setattr(VN,'B2Geometry',SafeGeometry)
 forecast=NS(rs=NS(trk=NS(now={TARGET:(None,None,None)})))
 out=n._propose(NS(),None,sim.start,sim.hold,sim.prefix,forecast,prefs,None)
 assert out is not marker and not delegated
 assert out.stage=='manual_commitment' and out.details['vault_approach'] and out.details['entry_kind']=='approach'
 assert out.mask==B['L'] and out.move.family=='VAULT_IDLE'
 assert n._vault_responsibility[out.move][0].family=='CC_JUMP_CAST'  # the buddy's own jump family keeps the HP


def walking(raw,direction,way):
 """The scene's target walking at 8 u/s: way +1 toward her (incoming), -1 away from her."""
 t=raw['ents'][0];t['fsms'][0]['state']='Walk';t['vel']=[-direction*way*8.,0.]
 return raw


@pytest.mark.parametrize('state,way,kind',[('Walk',1,'approach'),('Walk',-1,'hop_hook'),('Idle',0,'hop_hook')])
def test_only_an_incoming_walker_is_approached_inside_the_hook_range(state,way,kind):
 # #298 decision 1: an incoming walker is approached to the near jump; Idle / receding walkers keep the hook range
 n,raw,sim,ctx=M.entry_scene(-1,7.)
 if state=='Walk':walking(raw,-1,way)
 assert V.incoming_walk(raw['ents'][0],raw['hero']['pos'][0])==(way==1)
 (got,req),=manual_entries(n,raw,sim,ctx)
 assert got==kind and (req['far'] is None)==(kind=='approach')


def test_incoming_walker_approach_skips_the_hook_range_and_takes_the_near_jump():
 n,raw,sim,ctx=M.entry_scene(-1,12.);walking(raw,-1,1)
 (kind,req),=manual_entries(n,raw,sim,ctx)
 r=n.runner;r.anchor.open(req);r.step(sim.f,raw,True,True,t_game=10.,sim=sim,bombs=BOMBS)
 assert kind=='approach' and r.run.link=='approach'
 _,mid,_,_=M.entry_scene(-1,7.);walking(mid,-1,1);mid['f']=raw['f']+1
 m=r.step(sim.f+1,mid,True,True,t_game=10.+1/60,sim=sim,bombs=BOMBS)
 assert r.run.link=='approach' and m==B['L'] and r.run.v['req']['far'] is None  # 7 u: no hook, still running in
 _,close,_,_=M.entry_scene(-1,4.2);walking(close,-1,1);close['f']=raw['f']+2
 m=r.step(sim.f+2,close,True,True,t_game=10.+2/60,sim=sim,bombs=BOMBS)
 assert r.run.link=='near' and m&B['J'] and r.run.v['row']['F0']==close['f']+2


def test_no_hook_flag_keeps_the_near_entry_and_drops_only_the_hook():
 hb=[19.75,3.015,20.25,5.094];hero={'box':hb,'pos':[20.,4.5],'can':{'harpoon':True},'silk':9,'tm':{'atk_cd':0.}}
 for root,kind in ((5.,'near'),(7.,None)):
  x=20.+root;box=[x-2.252,3.015,x+1.341,6.917]
  assert V.distance_entry(CFG,hero,[x,7.449],box,1,.25,hook=False)[0]==kind


# #300 D1 (plan 7.164): the approach's 24 frames are frames of CONFIRMED running; at most 4 start-up frames
# (SEND 2 + HF 2) to confirm it and 28 frames from the admission in any case. Live 786: the legal early entry 2578 had
# the planner's R latched with a queued release (dropped 2580-2581, the approach's R kept from 2582) and was refused
# at 2603 at age 25 although she stood where the 2579 entry stood.
L,R=B['L'],B['R']


@pytest.mark.parametrize('hf,nxt,ok',[
 ({'latched':L,'desired':L,'pending':0},L,True),
 ({'latched':L|B['J'],'desired':L|B['J'],'pending':0},L,True),         # other keys do not matter
 ({'latched':L,'desired':0,'pending':1},L,False),                       # a queued release drops it again
 ({'latched':L,'desired':L,'pending':2},L,False),                       # release + press queued: it drops first
 ({'latched':L,'desired':L,'pending':0},0,False),                       # the previous owner's in-flight 0 releases it
 ({'latched':0,'desired':L,'pending':1},L,False),                       # sent / desired is no latch
 ({'latched':R,'desired':R,'pending':0},R,False),                       # the wrong way
 ({'latched':True,'desired':L,'pending':0},L,False),                    # malformed fields are no confirmation
 (None,L,False)])
def test_running_is_confirmed_only_by_the_actual_latch_kept(hf,nxt,ok):
 bit=L.bit_length()-1
 state={'act':{} if hf is None else {'hf':{'latched':hf['latched'],'desired':hf['desired'],
                                          'pending':[hf['pending'] if i==bit else 0 for i in range(22)],'age':[3]*22}}}
 assert V.running_confirmed(state,np.array([nxt],np.int64),-1) is ok
 assert not V.running_confirmed({'act':{'hf':{'latched':L,'desired':L,'pending':[0]*5}}},np.array([L]),-1)
 assert not V.running_confirmed(state,np.zeros(0,np.int64),-1)


def approach_run(direction=-1):
 n,raw,sim,ctx=M.entry_scene(direction,12.)
 (_,req),=manual_entries(n,raw,sim,ctx)
 r=n.runner;r.anchor.open(req)
 return r,raw,sim


def tick(r,raw,sim,k,*,key=None,**kw):
 """Step the approach k frames after its admission with the STATE's latch `key` (None: nothing latched)."""
 raw['f']=sim.f+k
 s=held(raw,sim,key,**kw) if key is not None else held(raw,sim,0,nxt=0)
 return r.step(sim.f+k,raw,True,True,t_game=10.+k/60,sim=s,bombs=BOMBS)


@pytest.mark.parametrize('confirm_at,bound',[(0,True),(3,True),(4,True),(None,False)])
def test_the_start_is_bound_at_the_first_confirmed_latch_inside_the_start_up_frames(confirm_at,bound):
 r,raw,sim=approach_run()
 for k in range(0,5):
  m=tick(r,raw,sim,k,key=L if k==confirm_at else None)
  if r.run is None:break
  assert m==L and r.run.link=='approach'
 if bound:
  assert r.run is not None and r.run.v['run_f']==sim.f+confirm_at
 else:  # nothing confirmed by admission + 4: refused at that tick, never a default start
  assert r.run is None and 'start-up' in r.done[-1].v['why'] and r.done[-1].v['closed_f']==sim.f+4


def test_admission_latch_that_a_queued_release_drops_is_no_start():
 r,raw,sim=approach_run()
 tick(r,raw,sim,0,key=L,desired=0,pending=1)       # the planner's L, released again 2 frames on
 assert r.run.v['run_f'] is None
 tick(r,raw,sim,1,key=L,desired=L,pending=0,nxt=0)  # still the previous owner's in-flight neutral
 assert r.run.v['run_f'] is None
 tick(r,raw,sim,3,key=L)
 assert r.run.v['run_f']==sim.f+3


def test_a_bound_start_is_never_restarted_and_counts_the_running_frames():
 r,raw,sim=approach_run()
 tick(r,raw,sim,2,key=L)
 assert r.run.v['run_f']==sim.f+2
 tick(r,raw,sim,5)                                  # released for a frame: no rebinding, no start-up refusal
 tick(r,raw,sim,6,key=L)
 assert r.run.v['run_f']==sim.f+2 and r.run.link=='approach'
 assert tick(r,raw,sim,2+24,key=L)==L and r.run is not None
 assert tick(r,raw,sim,2+25,key=L) is None and 'no table range within its frames' in r.done[-1].v['why']
