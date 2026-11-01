from pathlib import Path
from types import SimpleNamespace as NS
import json
import numpy as np
import pytest
from ssbot.combat import observed_slam as O,attack_range as A,forum_planner as F

def tracker(monkeypatch,enabled):
    monkeypatch.setattr(O,'ENABLED',enabled)
    monkeypatch.setattr(O,'MOTION_ENABLED',True)
    tab=A.load_table(A.table_path(A.SPECS[O.CLAPPER]),A.SPECS[O.CLAPPER])
    tr=A.RangeTracker({O.CLAPPER:tab});fc=0
    for f in range(300,356):
        fs=0 if f==354 else 1;fc+=fs
        state='Slam Antic' if f<349 else 'Slam 0' if f<354 else 'Slam 1'
        state_start=300 if f<349 else 349 if f<354 else 354
        n=max(0,min(f-349,4));extra=.6 if f==355 else 0
        x=26+.6*n-(.1 if f==355 else 0)
        def ent(iid,px,vx):return {'type_key':O.CLAPPER,'iid':iid,'pos':[px,7.4,0.],'vel':[vx,0.],
            'flipX':True,'hp':10,'hidden':False,'is_dead':False,'colliders':[],
            'fsms':[{'name':'Control','state':state,'t':(f-state_start)/60}]}
        raw={'f':f,'fc':fc,'fs':fs,'ts':1.,'dt':1/60,'fdt':.02,'hero':{'pos':[32.,10.]},
             'ents':[ent(1,x,0. if f==355 or f<349 else 30.),ent(2,38+.6*n+extra,0. if f<349 else 30.)]}
        tr.feed(raw)
    return tr,tab

def test_support_and_direct_paths_share_explicit_instance_offset(monkeypatch):
    # Isolate stopped-motion displacement; both sides retain the same opted-in
    # damage-clock shapes. The baseline has no accepted stop instance.
    base,tab=tracker(monkeypatch,True);base.observed_motion.by_iid.clear()
    old_masks={k:base.estimate(1,k).raw for k in [0,1,2,12]}
    targets=[NS(iid=1,hazard=False),NS(iid=2,hazard=False),NS(iid=3,hazard=True),NS(iid=1,hazard=False)]
    tb=np.tile(np.array([[27.,3.,31.,7.],[39.,3.,43.,7.],[24.,2.,25.,3.],[27.,3.,31.,7.]])[:,None,:],(1,13,1))
    old=F.ForumPlanner._ds_move_paths(base,targets,tb)
    live,_=tracker(monkeypatch,True);assert live.observed_stop(1) is not None and live.observed_stop(2) is None
    assert A.bin_of(live.T-live.now[1][2].t0)==55
    new=F.ForumPlanner._ds_move_paths(live,targets,tb);assert set(new)==set(old)=={0,1,3}
    for ti,paths in new.items():
        for j,p in enumerate(paths):
            np.testing.assert_array_equal(p[0],old[ti][j][0]);np.testing.assert_array_equal(p[:,[1,3]],old[ti][j][:,[1,3]])
            if ti in (0,3):np.testing.assert_array_equal(p[:,[0,2]],np.tile(tb[ti,0,[0,2]],(13,1)))
            else:np.testing.assert_array_equal(p,old[ti][j])
    for k,prior in old_masks.items():
        curr=live.estimate(1,k).raw
        np.testing.assert_array_equal(curr.m,prior.m);assert curr.iy0==prior.iy0
        assert curr.ix0-prior.ix0==(-12 if k else 0)
    # One table is shared; another instance's estimate cannot inherit the stop.
    for k in [0,1,12]:
        p=base.estimate(2,k).raw;q=live.estimate(2,k).raw
        np.testing.assert_array_equal(p.m,q.m);assert (p.ix0,p.iy0)==(q.ix0,q.iy0)

def test_foreign_instance_token_cannot_freeze_the_path(monkeypatch):
    tr,tab=tracker(monkeypatch,True);a=tr.now[1][2];b=tr.now[2][2];stop=tr.observed_stop(1)[1]
    tp=tab.templates[(b.fam,'main')];bn=A.bin_of(tr.T-b.t0)
    got=O.predicted_offset(tab,b,tp,bn,bn+1,stop)
    p=tab.position(tp,bn,(b.x0,b.y0),b.s,b.hero_du,b.fam);q=tab.position(tp,bn+1,(b.x0,b.y0),b.s,b.hero_du,b.fam)
    assert got==(q[0]-p[0],q[1]-p[1]) and got[0]>.5

@pytest.mark.parametrize('value',[None,'2','true'])
def test_invalid_feature_value_rejected(value):
    with pytest.raises(ValueError):O._flag(value)

def test_model_revision_binds_runtime_flag(monkeypatch):
    monkeypatch.setattr(O,'ENABLED',False);a=O.revision_fields()
    monkeypatch.setattr(O,'ENABLED',True);b=O.revision_fields()
    assert a!=b and a['observed_slam'] is False and b['observed_slam'] is True

def test_finite_kernel_is_warmed_before_remaining_fight_kernels(monkeypatch):
    from ssbot.combat import seen_lifetime as L
    monkeypatch.setattr(O,'ENABLED',True);monkeypatch.setattr(O,'FINITE_ENABLED',True)
    monkeypatch.setattr(F.Planner,'warm_kernels',lambda _:None)
    monkeypatch.setattr(F,'seen_contacts',lambda *a:None);monkeypatch.setattr(F,'seen_contacts_swept',lambda *a:None)
    class Done(Exception):pass
    calls=[]
    def probe(*args):
        assert np.isfinite(args[9]).all() and args[0].dtype==np.float64 and args[1].dtype==np.bool_
        calls.append(args[-1])
        if args[-1]:raise Done()
    monkeypatch.setattr(L,'timed_seen',probe)
    with pytest.raises(Done):F.ForumPlanner.warm_kernels(F.ForumPlanner.__new__(F.ForumPlanner))
    assert calls==[False,True]

def test_model_flag_changes_shared_budget_revision(tmp_path,monkeypatch):
    from ssbot.combat import knife_chain_b2 as B,knife_chain_slam as S
    from ssbot.combat.knife_chain_budget import LearningStop
    monkeypatch.setattr(S,'load_runner',lambda:NS(cfg0={}))
    class Bare(B.NativeChainB2):
        def __init__(self,**kw):self.__dict__.update(kw)
    for key,value in {'SSBOT_FORUM_CHAIN_B2':'1','SSBOT_FORUM_CHAIN_BATCH':'test-model-profile','SSBOT_FORUM_CHAIN_ARM':'A',
            'SSBOT_FORUM_CHAIN_BUDGET':str(tmp_path/'ledger.json'),'SSBOT_FORUM_CHAIN_FAST_HOOK':'0'}.items():monkeypatch.setenv(key,value)
    monkeypatch.setattr(O,'ENABLED',False);first=Bare.from_env(journal=str(tmp_path/'events.jsonl'))
    before=(tmp_path/'ledger.json').read_bytes();monkeypatch.setattr(O,'ENABLED',True)
    with pytest.raises(LearningStop,match='revision'):Bare.from_env(journal=str(tmp_path/'events2.jsonl'))
    assert (tmp_path/'ledger.json').read_bytes()==before

def test_model_flag_has_actual_effective_binding_and_construction_conflict(tmp_path):
    from ssbot.train.forum_measure_manifest import configuration_manifest
    root=tmp_path/'ssbot';(root/'combat').mkdir(parents=True)
    (root/'combat/observed_slam.py').write_text("import os\nENABLED = os.environ.get('SSBOT_FORUM_OBSERVED_SLAM','0') == '1'\n")
    modules={'ssbot.combat.observed_slam':NS(ENABLED=True)}
    one=configuration_manifest(root,NS(chain_native=None),environ={'SSBOT_FORUM_OBSERVED_SLAM':'1'},modules=modules)
    entry=one['switches']['SSBOT_FORUM_OBSERVED_SLAM'];assert entry['resolution']=='runtime_binding' and entry['role']=='control'
    assert entry['effective']=={'ssbot.combat.observed_slam.ENABLED':True}
    p=NS(chain_native=NS(_environment=(('SSBOT_FORUM_OBSERVED_SLAM','0'),)))
    bad=configuration_manifest(root,p,environ={'SSBOT_FORUM_OBSERVED_SLAM':'1'},modules=modules)
    assert 'SSBOT_FORUM_OBSERVED_SLAM: environment changed after construction' in bad['unresolved']

@pytest.mark.parametrize('frame',[10,11,10.0,True,None])
def test_seen_lifetime_requires_current_integer_frame_and_preserves_order(frame):
    raw={'f':frame,'dt':1/60,'fdt':.02,'ts':1.}
    inst=NS(fam='CC_SLAM',states=['Slam 1'])
    rt=NS(observed_motion=NS(clock=raw),now={1:(O.CLAPPER,{'hp':10},inst)})
    tr=NS(state='Slam 1',t_entry=1.,table=NS(dwell={'Slam 1':(.04,.06)}))
    forecast=NS(rs=NS(trk=rt,focus=1),origin_t=1.02,fc=NS(trackers={1:tr}))
    hammer=NS(name='Slam Collider 1',active=True,poly=[(0,0),(1,0),(0,1)])
    body=NS(name=O.CLAPPER,active=True,poly=[(0,0),(1,0),(0,1)])
    ent=NS(id=1,type_key=NS(v=O.CLAPPER),fsm=[('Control','Slam 1',.02)],dmg_boxes=[hammer,body])
    ws=NS(stamp=NS(frame=10),entities=[ent])
    out=O.seen_expiries(ws,forecast)
    if isinstance(frame,int) and not isinstance(frame,bool) and frame==10:
        assert len(out)==2 and np.isfinite(out[0]) and np.isinf(out[1])
    else:assert out is None
