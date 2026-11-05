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
 assert kind=='approach' and req['approach']=={'max_f':CFG['APPROACH']['max_f']}
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


@pytest.mark.parametrize('case,closed,why',[('buddy_landed','abort',"jump is over"),
                                            ('airborne','abort','off the ground'),
                                            ('timeout','abort','no table range within its frames'),
                                            ('target_moved','done','left Idle / Walk')])
def test_approach_ends_with_an_explicit_reason(case,closed,why):
 n,raw,sim,ctx=M.entry_scene(-1,12.)
 (_,req),=manual_entries(n,raw,sim,ctx)
 r=n.runner;r.anchor.open(req);r.step(sim.f,raw,True,True,t_game=10.,sim=sim,bombs=BOMBS)
 f=sim.f+(CFG['APPROACH']['max_f']+1 if case=='timeout' else 1);raw['f']=f
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
