"""Observation-only restoration of sprint attack-cancel velocity, never a new move."""
from copy import deepcopy
import numpy as np
import pytest
from ssbot.knowledge import kinematics as K


def params():
 return K.hero2(K.HeroParams.load(__import__('pathlib').Path(__file__).parents[2]/'knowledge/1.0.30000/kinematics/hero_wanderer_forum.json'),on=True)


def push(fr,f,md=K.M_NORMAL,vx=-23.6,flags=None,mask=0,face=-1,**kw):
 flags=flags or {};r={'f':f,'fs':1,'dt':1/60,'udt':1/60,'facing':face,'wall':0,'mask':mask,
  'vel':[vx,-6.],'valid':True,'load':False,**kw}
 s=K.initial_state(fr.p,30.,10.,vx=vx,ground=False).reshape(K.K)
 s[K.ATTACKING]=float(flags.get('attacking',False))
 fr.push(s,r,md,lambda name:bool(flags.get(name,False)))
 return s


def armed(p=None):
 fr=K.ForumRows(p or params());push(fr,10,K.M_SPRINT,vx=-24.7,mask=K.B_ATTACK)
 return fr


def test_observed_air_attack_cancel_restores_current_velocity_not_old_sprint_speed():
 fr=armed();s=push(fr,11,flags={'attacking':True})
 assert s[K.XVX]==-23.6 and s[K.XVXD]==0
 s=push(fr,12,vx=-18.88,flags={'attacking':True},fs=0)
 assert s[K.XVX]==-18.88  # no extrapolation/extra decay on a zero-physics frame


@pytest.mark.parametrize('case',[
 'plain_end','ground','grounded_sprint','turn','wall','slide','cling','gap','duplicate',
 'invalid','load','recoil','nan_velocity','zero_velocity','no_history','old_attack','ground_sprint_phase',
])
def test_unknown_or_other_transition_never_invents_cancel_velocity(case):
 fr=armed();kw={'flags':{'attacking':True}};f=11
 if case=='plain_end':kw['flags']={}
 if case=='ground':kw['flags']['onGround']=True
 if case=='grounded_sprint':
  fr=K.ForumRows(params());push(fr,10,K.M_SPRINT,flags={'onGround':True})
 if case=='ground_sprint_phase':
  fr=K.ForumRows(params());push(fr,10,K.M_SPRINT,clip='Sprint')
 if case=='turn':kw['face']=1
 if case=='wall':kw['wall']=-1
 if case=='slide':kw['flags']['wallSliding']=True
 if case=='cling':kw['flags']['wallClinging']=True
 if case=='gap':f=12
 if case=='duplicate':f=10
 if case=='invalid':kw['valid']=False
 if case=='load':kw['load']=True
 if case=='recoil':kw['flags']['recoilingLeft']=True
 if case=='nan_velocity':kw['vx']=float('nan')
 if case=='zero_velocity':kw['vx']=0.
 if case=='no_history':fr=K.ForumRows(params())
 if case=='old_attack':
  fr=K.ForumRows(params());push(fr,10,K.M_SPRINT,flags={'attacking':True})
 s=push(fr,f,**kw);assert s[K.XVX]==0
 # An unknown transition cannot arm a latent flag that revives one tick later.
 assert push(fr,f+1,flags={'attacking':True})[K.XVX]==0


@pytest.mark.parametrize('event',['ground','turn','wall','mode','load','gap'])
def test_broken_provenance_cannot_resurrect_after_the_break(event):
 fr=armed();assert push(fr,11,flags={'attacking':True})[K.XVX]!=0
 kw={};f=12
 if event=='ground':kw['flags']={'onGround':True}
 if event=='turn':kw['face']=1
 if event=='wall':kw['wall']=-1
 if event=='mode':kw['md']=K.M_GLIDE
 if event=='load':kw['load']=True
 if event=='gap':f=13
 push(fr,f,**kw)
 assert push(fr,f+1,flags={'attacking':True})[K.XVX]==0


def test_held_direction_is_unobservable_then_releases_without_predicting_hidden_velocity():
 fr=K.ForumRows(params());push(fr,10,K.M_SPRINT,mask=K.B_LEFT)
 assert push(fr,11,flags={'attacking':True},mask=K.B_LEFT)[K.XVX]==0
 assert push(fr,12,flags={'attacking':True},mask=0)[K.XVX]==0
 assert push(fr,13,flags={'attacking':True},mask=0,vx=-15.104)[K.XVX]==-15.104


def test_disabled_hero2_rule_never_restores_xvx():
 p=params();p.hero2=int(p.hero2)&~K.H2_SPR_ATK
 assert push(armed(p),11,flags={'attacking':True})[K.XVX]==0


def test_live_and_batch_estimators_restore_the_same_row_from_causal_states():
 from tests.test_kinematics import _state
 p=params();seq=[]
 for f in range(3):
  s=_state(f,30.,10.,onGround=False,isSprinting=f==0,attacking=f>0);s['hero'].update(facing=-1,vel=[-24.7 if f==0 else -23.6, -6.],
    anim={'clip':'Sprint Air' if f==0 else 'DownSlashAlt'},hero_state=7 if f==0 else 0,
    control_relinquished=f==0,wall=[False,False]);s['act']={'mask':K.B_ATTACK};seq.append(s)
 tr=K.Trace.from_states(seq,p);ref=K.estimate_state(tr,np.arange(len(tr)),p)
 tracker=K.StateTracker(p);cols=[]
 for s in seq:tracker.push(s);cols.append(tracker.state().reshape(K.K).copy())
 actual=np.column_stack(cols);np.testing.assert_allclose(actual,ref,rtol=0,atol=1e-5)
 assert actual[K.XVX,1]==-23.6 and actual[K.XVX,2]==-23.6
