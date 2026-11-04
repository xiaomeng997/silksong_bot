"""A sent/accepted knife's conditional hit cannot erase other danger or become a real receipt."""
from copy import deepcopy
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_transfer import TransferPlan,TransferGoal
from ssbot.combat.knife_chain_commitment import MoveInstance,PathContact,ContactScan
from ssbot.combat import knife_chain_air_native as N


def setup(monkeypatch,case):
 from tests.test_knife_chain_transfer import transfer_motion_scene
 from ssbot.combat.air_chain import ChainSim
 _,s,old=transfer_motion_scene(K.M_NORMAL)
 s['f']=1040;s['hero'].update(pos=[38.,9.253],box=[37.75,7.7,38.25,9.779],vel=[0.,-2.],
   silk=9,anim={'clip':'DownSlashAlt'},can={'attack':True,'input':True})
 s['hero']['tm']['atk_cd']=.1
 e=s['ents'][1];dx=38.-e['pos'][0];e['pos'][0]=38.;e['vel']=[0.,0.];e['fsms'][0].update(state='Slam Antic',t=5/60)
 for c in e['colliders']:
  c['verts_world'][::2]=[v+dx for v in c['verts_world'][::2]]
  c.update(layer=11,damage={'hazard_type':1,'flags':0,'eff':2,'can_cause_damage':True})
 S=K.initial_state(old.params,38.,9.253,vy=-2.,ground=False).reshape(K.K);S[K.ATTACKING]=1.;S[K.ATK_PDIR]=2.;S[K.ATK_T]=.05
 if case=='body_overlap':
  S[K.PY]=6.;s['hero']['pos'][1]=6.;s['hero']['box']=[37.75,4.4473,38.25,6.5262]
 if case=='hammer':e['colliders'].append({'name':'Slam Collider 1','enabled':True,'layer':22,'damage':{'hazard_type':1,'flags':0}})
 if case=='unknown_damage':e['colliders'][0]['damage']=None
 if case=='unknown_hammer':e['colliders'].append({'name':'Slam Collider 1','enabled':True,'layer':22,'damage':None})
 if case=='unknown_enabled':e['colliders'][0]['enabled']=None
 if case=='late_antic':e['fsms'][0]['t']=46/60
 if case=='boundary_antic':e['fsms'][0]['t']=44/60
 if case=='unknown_clock':e['fsms'][0]['t']=None
 if case=='damage_flags':e['colliders'][0]['damage']['flags']=1
 if case=='moving':e['vel'][0]=1.
 if case=='state_zero':e['fsms'][0]['state']='Slam 0'
 sim=ChainSim(S,np.array([B['R']|B['D']],np.int64),old.hold,old.params,old.terrain,1040,1040)
 n=N.NativeManualAirChain(runner_factory=load_runner,probe_ref='conditional244');n.reset(0,start_frame=1040)
 p=TransferPlan(8,7,990,1000,0.,B['R'],0,0,0,False,1040,40)
 n.runner.run=Run('rune_transfer','strike',p.variables())
 n.runner.run.v['row']={'F0':1036,'press_F':1037,'contact_frame':1041,'masks':[B['R']|B['D']]*16}
 n._transfer_goal=TransferGoal(8,7,990,0.,'CAST',MoveInstance(7,990,'CC_CAST'))
 n.commitment={'move':p.move,'origin':1000,'ta':0.,'predicted_bounce':None}
 n._transfer_responsibility[p.move]=(MoveInstance(7,990,'CC_CAST'),0.)
 n._transfer_target_moves[p.move]=(MoveInstance(8,1035,'CC_SLAM'),.65)
 n._press=1037;n._accepted=1037;n._actual_state=s;n._clock=1.;n._clock_known=True
 n._context=(None,None,None,np.zeros((0,6)))
 if case=='unsent':n._press=None
 if case=='unaccepted':n._accepted=None
 if case=='different_commit':n.commitment['move']=MoveInstance(8,1001,'RUNE_TRANSFER');n._transfer_responsibility[n.commitment['move']]=(MoveInstance(7,990,'CC_CAST'),0.)
 if case=='expired':n.runner.run.v['row']['contact_frame']=1039
 if case=='unbound':n._transfer_target_moves.clear()
 monkeypatch.setattr(n,'queued_prefix',lambda *a:(int(sim.prefix[0]),'actual fixture'))
 seen=deepcopy(s);seen['f']=1035;n._ticks.append((1035,seen,.65,False,True))
 owner=7 if case=='other_owner' else None if case=='unknown_owner' else 8
 kind='delayed' if case=='delayed' else 'other' if case=='unknown_kind' else 'move'
 scans=[]
 class Geo:
  def __init__(self,*a):pass
  @staticmethod
  def ref(p):return 'actual-check'
  def preflight(self,p):raise AssertionError('attacking target must keep full-owner geometry')
  def scan(self,p):
   scans.append(p)
   return ContactScan(self.ref(p),p.origin,p.through,(PathContact(p.through,owner,kind),),'all-owner fixture')
 monkeypatch.setattr(N,'B2Geometry',Geo)
 fc=NS(rs=NS(trk=NS(now={8:(None,None,NS(fam='CC_SLAM',t0=.65))},T=1.)))
 return n,s,sim,fc,scans


@pytest.mark.parametrize('case,allowed',[
 ('body_padding_after_hit',True),('other_owner',False),('delayed',False),('unknown_owner',False),
 ('unknown_kind',False),('hammer',False),('unknown_damage',False),('late_antic',False),
 ('moving',False),('state_zero',False),('body_overlap',False),('unsent',False),
 ('unaccepted',False),('different_commit',False),('expired',False),
 ('unbound',False),('boundary_antic',False),('unknown_clock',False),('damage_flags',False),
 ('unknown_hammer',False),('unknown_enabled',False),
])
def test_accepted_conditional_hit_only_removes_postcontact_target_padding(monkeypatch,case,allowed):
 n,s,sim,fc,scans=setup(monkeypatch,case)
 offer=n._transfer_offer(s,0.,sim,fc,NS(target=8),False)
 assert (offer is not None)==allowed
 assert len(scans)==(0 if case in {'unbound','unknown_enabled'} else 1)
 if case in ('body_padding_after_hit','other_owner','delayed','unknown_owner','unknown_kind'):
  check=scans[0]
  assert check.flags[-1]&K.F_INVULN  # modeled hit branch, never a receipt
  assert not check.check_flags[-1]&K.F_INVULN  # no new global protection for ANY owner/hazard
 if allowed:
  assert n.commitment is not None and n._hit is None and n.post_context is None
  assert not offer.draft.run.v.get('bounced',False)
  assert offer.details['conditional_hit_check'] and offer.details['conditional_contact']==1041
  assert offer.mask==B['R']|B['D']  # original absolute row, no new keys or timing


def test_only_actual_following_hit_and_bounce_reopens_real_post_context(monkeypatch):
 n,s,sim,fc,scans=setup(monkeypatch,'body_padding_after_hit')
 offer=n._transfer_offer(s,0.,sim,fc,NS(target=8),False)
 assert offer is not None and n.post_context is None and n._hit is None
 actual=deepcopy(s);actual.update(f=1041,dt=1/60)
 actual['hero'].update(cstate_int=[0,8],anim={'clip':'Recoil Twirl'})
 actual['act'].update(target=1041,applied=1041,mask=int(sim.prefix[0]))
 actual['ev']=[{'k':'hit','f':1041,'d':{'ent':8,'src':'DownSlash'}}]
 n.begin(actual)
 assert n.commitment is None and n.post_context['hit']==1041
 assert n.post_context['move']==offer.move
