from types import SimpleNamespace as NS
from copy import deepcopy
import pytest
from ssbot.combat.observed_slam import Monitor

def _stopped(m, iid, inst): return m.stop_for(iid, inst) is not None
def make(frame,fixed,x,state='Slam 0',vx=30,fs=1,**overrides):
 e={'pos':[x,7.4],'vel':[vx,0.],'flipX':True,'hp':10.,'fsms':[{'name':'Control','state':state}]}
 raw={'f':frame,'fc':fixed,'fs':fs,'ts':1.,'dt':1/60,'fdt':.02}
 for k,v in overrides.items():
  (e if k in e else raw)[k]=v
 return raw,e
def feed(m,inst,args):
 raw,e=args;m.feed(raw,{7:('Song Heavy Sentry',e,inst)})
def init():
 m=Monitor();i=NS(fam='CC_SLAM',s=1);feed(m,i,make(10,8,0,'Slam Antic',0));return m,i
def arm(m,i):feed(m,i,make(11,9,0));feed(m,i,make(12,10,.6))
def test_entry_not_stop():
 m,i=init();feed(m,i,make(11,9,0));assert not _stopped(m,7,i)
def test_real_stop_and_current_root():
 m,i=init();arm(m,i);feed(m,i,make(13,11,.6,'Slam 1',0));assert _stopped(m,7,i) and m.by_iid[7].x==.6
 assert m.stops==1 and m.by_iid[7].stop_f==13
def test_no_fixed_step_not_stop():
 m,i=init();arm(m,i);feed(m,i,make(13,10,.6,fs=0));assert not _stopped(m,7,i)
def test_moving_zero_velocity_not_stop():
 m,i=init();arm(m,i);feed(m,i,make(13,11,1.2,'Slam 2',0));assert not _stopped(m,7,i)
def test_motion_resumes_clears_stop():
 m,i=init();arm(m,i);feed(m,i,make(13,11,.6,'Slam 1',0));feed(m,i,make(14,12,1.2,'Slam 1',30));assert not _stopped(m,7,i)
@pytest.mark.parametrize('change',[{'ts':0.},{'fc':99},{'f':14},{'fdt':None},{'hp':0.},{'flipX':False},{'pos':[float('nan'),7.]}])
def test_unknown_discontinuous_or_dead_resets(change):
 m,i=init();arm(m,i);feed(m,i,make(13,11,.6,'Slam 1',0,**change));assert not _stopped(m,7,i)
def test_same_iid_new_instance_not_reuse():
 m,i=init();arm(m,i);j=NS(fam='CC_SLAM',s=1);feed(m,j,make(13,11,.6,'Slam 1',0));assert not _stopped(m,7,j)
def test_missing_antic_not_trusted():
 m=Monitor();i=NS(fam='CC_SLAM',s=1);feed(m,i,make(11,9,0));feed(m,i,make(12,10,.6));feed(m,i,make(13,11,.6,'Slam 1',0));assert not _stopped(m,7,i)
def test_antic_recoil_cannot_arm():
 m,i=init();feed(m,i,make(11,9,.06,'Slam Antic',0));feed(m,i,make(12,10,.06,'Slam Antic',0));assert not _stopped(m,7,i) and not m.by_iid[7].armed
