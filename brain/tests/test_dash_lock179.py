"""Task 179 (#296, live 786 2617): an air-dash impulse is checked through the motion it locks, never N2 only.

Live w13_pose178 786766c3: from the wall at 2617 the transfer sent DASH+R (2619); the dash and the input-less Sprint
Air Short after it carried her into the 2628 Slam 2 while every two-frame step was clear. The new dash is now scanned
from the send through the modeled input return plus the send delay on the actual prefix, hold and abilities; a
blocked or unknown lock never starts a fresh transfer and hands an active Run back through B2 recovery. A fresh
transfer never starts inside a dash or relinquished motion (2607 bound the SWITCH inside her leftward air dash).
"""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_commitment import ContactScan,PathContact
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.knowledge import kinematics as K
from tests.test_shared_strike_approach import flight
from tests.test_target_entry_attack import native

FC=NS(rs=NS(trk=NS(now={8:(None,None,None)})))
LOCKED=(K.M_DASH,*K.RELINQUISHED,*K.NO_INPUT)


def chain(monkeypatch,r):
 n=native();n.runner=r;n._transfer_ready=True;n._context=(None,None,None,np.zeros((0,6)))
 n._transfer_goal=T.TransferGoal(8,7,990,0.)
 monkeypatch.setattr(n,'queued_prefix',lambda *a:(0,'known test prefix'))
 return n


def geometry(monkeypatch,contact=None):
 """All-owner scans: one contact at frame `contact` once a path reaches it (None: always clear)."""
 from ssbot.combat import knife_chain_air_native as N
 scans=[]
 class Geo:
  def __init__(self,*a):pass
  def scan(self,path):
   scans.append(path)
   hit=() if contact is None or path.through<contact else (PathContact(contact,7,'move'),)
   return ContactScan('fixture',path.origin,path.through,hit,'all-owner')
  preflight=scan
 monkeypatch.setattr(N,'B2Geometry',Geo)
 return scans


def lock_info():
 r,s,sim=flight();draft,p,path,mask=T.propose(r,s,0.,sim,8,False,np.zeros((0,6)),set())
 scans=[]
 lock,info=native()._dash_lock_scan(sim,p,mask,0.,NS(scan=lambda q:scans.append(q) or NS(complete=True,contacts=())),'air')
 return mask,lock,info,scans[-1]


def test_locked_mode_names_dash_relinquished_and_no_input_motion_only():
 S=np.zeros(K.K);S[K.MODE]=K.M_NORMAL
 assert NativeManualAirChain._locked_mode(NS(start=S)) is None
 for mode in LOCKED:
  S[K.MODE]=mode
  assert NativeManualAirChain._locked_mode(NS(start=S.reshape(K.K,1)))==mode
 assert NativeManualAirChain._locked_mode(NS()) is None


def test_dash_scan_runs_from_the_send_through_input_return_plus_the_send_delay():
 mask,lock,info,checked=lock_info()
 assert mask&B['DASH'] and lock.complete
 modes=np.asarray(checked.states[K.MODE]);flags=np.asarray(checked.flags)
 j0,j1=info['dash_frame']-checked.origin,info['input_frame']-checked.origin
 assert modes[j0]==K.M_DASH and j0 in (2,3)  # the impulse applies at the send's target frame
 locked=np.isin(modes,LOCKED)|((flags&(K.F_RELINQ|K.F_NO_INPUT))!=0)
 assert locked[j0:j1].all() and not locked[j1]
 assert checked.through==info['input_frame']+2==info['checked_through']
 assert checked.through-checked.origin>2  # the old gate stopped at origin+2


@pytest.mark.parametrize('where',['inside','after'])
def test_fresh_dash_is_refused_by_a_contact_inside_its_lock_not_one_after_it(monkeypatch,where):
 _,_,info,_=lock_info()
 contact=info['input_frame'] if where=='inside' else info['checked_through']+1
 r,s,sim=flight();r.run=None;n=chain(monkeypatch,r)
 scans=geometry(monkeypatch,contact)
 offer=n._transfer_offer(s,0.,sim,FC,NS(target=8),False)
 events={e['event']:e for e in n.events}
 if where=='inside':
  assert offer is None and n.runner.run is None and n.commitment is None and not n._receipts
  refused=events['rune_transfer_dash_refused']
  assert refused['first']['frame']==contact and refused['owner']=='current owner keeps the keys'
  assert len(scans)==1 and scans[0].through==info['checked_through']
 else:
  assert offer is not None and offer.mask&B['DASH'] and 'rune_transfer_dash_refused' not in events
  assert events['rune_transfer_dash_checked']['input_frame']==info['input_frame']
  assert [q.through for q in scans]==[info['checked_through'],sim.f+2]  # then the ordinary current step


def test_unknown_lock_end_is_refused_not_passed(monkeypatch):
 r,s,sim=flight();r.run=None;n=chain(monkeypatch,r);geometry(monkeypatch)
 n.DASH_LOCK_MAX=3  # input return not modeled inside the bound
 assert n._transfer_offer(s,0.,sim,FC,NS(target=8),False) is None
 refused=next(e for e in n.events if e['event']=='rune_transfer_dash_refused')
 assert refused['first'] is None and refused['complete'] is None and 'input return' in refused['reason']


def test_active_run_dash_refusal_hands_back_through_recovery(monkeypatch):
 r,s,sim=flight();n=chain(monkeypatch,r)
 assert r.run is not None and r.run.link=='air' and not r.run.v.get('approach_recipe')
 geometry(monkeypatch,sim.f+3)
 recovered=[];monkeypatch.setattr(n,'_recover',lambda reason,f:recovered.append((reason,f)))
 assert n._transfer_offer(s,0.,sim,FC,NS(target=8),False) is None
 assert recovered==[('rune transfer air dash refused: locked motion blocked or unknown',sim.f)]
 assert next(e for e in n.events if e['event']=='rune_transfer_dash_refused')['owner']=='B2 recovery hands back'


@pytest.mark.parametrize('mode',[K.M_DASH,K.M_SPRINT])
def test_no_fresh_transfer_inside_a_dash_or_relinquished_motion(monkeypatch,mode):
 from ssbot.combat import knife_chain_air_native as N
 r,s,sim=flight();r.run=None;n=chain(monkeypatch,r)
 np.asarray(sim.start).reshape(K.K,-1)[K.MODE]=mode
 monkeypatch.setattr(N.transfer,'propose',lambda *a,**kw:pytest.fail('a fresh transfer was planned inside locked motion'))
 assert n._transfer_offer(s,0.,sim,FC,NS(target=8),False) is None
 deferred=next(e for e in n.events if e['event']=='rune_transfer_start_deferred')
 assert deferred['mode']==mode and deferred['owner']=='current owner keeps the keys'
 assert n.runner.run is None and n.commitment is None


def ground_dash_scene(monkeypatch):
 """A fresh walk-link approach on the ground whose dash clock is due now (dash cooldown spent)."""
 from tests.test_knife_chain_transfer import transfer_motion_scene
 r,s,sim=transfer_motion_scene(K.M_NORMAL);r.run=None
 s['hero']['tm']['dash_cd']=0.
 n=chain(monkeypatch,r)
 monkeypatch.setattr(n,'queued_prefix',lambda *a:(int(sim.prefix[0]),'known test prefix'))
 return n,s,sim


def test_ground_dash_lock_ends_where_the_ground_sprint_takes_the_dash_release(monkeypatch):
 n,s,sim=ground_dash_scene(monkeypatch);scans=geometry(monkeypatch)
 offer=n._transfer_offer(s,0.,sim,FC,NS(target=8),True)
 assert offer is not None and offer.mask&B['DASH'] and offer.details['phase'] in ('walk','dash')
 checked=next(e for e in n.events if e['event']=='rune_transfer_dash_checked')
 lock=scans[0];modes=np.asarray(lock.states[K.MODE]);phase=np.asarray(lock.states[K.PHASE])
 j1=checked['input_frame']-lock.origin
 assert (modes[checked['dash_frame']-lock.origin:j1]==K.M_DASH).all()
 assert modes[j1]==K.M_SPRINT and phase[j1]==2 and lock.through==checked['input_frame']+2


def test_refused_ground_dash_keeps_the_same_run_running_without_the_impulse(monkeypatch):
 n,s,sim=ground_dash_scene(monkeypatch)
 scans=geometry(monkeypatch,sim.f+3)  # inside the dash itself
 offer=n._transfer_offer(s,0.,sim,FC,NS(target=8),True)
 assert offer is not None and not offer.mask&B['DASH'] and offer.mask&B['R'] and offer.stage=='manual_commitment'
 refused=next(e for e in n.events if e['event']=='rune_transfer_dash_refused')
 assert refused['first']['frame']==sim.f+3 and refused['owner']=='same transfer Run runs without the dash this tick'
 assert offer.path.assumptions['dash_refused']


def test_air_keys_in_closed_form_and_the_cut_path_equal_render_and_a_reroll():
 from ssbot.combat.knife_chain_air import model_path
 r,s,sim=flight();_,p,_,mask=T.propose(r,s,0.,sim,8,False,np.zeros((0,6)),set())
 n=native();scans=[]
 n._dash_lock_scan(sim,p,mask,0.,NS(scan=lambda q:scans.append(q) or NS(complete=True,contacts=())),'air')
 rendered=np.asarray(T.render(n.runner,p,p.entry_k,n.DASH_LOCK_MAX,'air'),np.int64);rendered[0]=mask
 cut=scans[-1];m=len(cut.commands)-len(sim.prefix)
 again=model_path(sim,p,rendered[:m],0.)
 assert np.array_equal(cut.commands,again.commands) and np.array_equal(cut.flags,again.flags)
 assert np.allclose(cut.box,again.box) and np.array_equal(cut.check_flags,again.check_flags) and cut.through==again.through
