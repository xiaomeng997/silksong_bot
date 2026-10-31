import math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import forum_planner as F
from ssbot.combat.seen_lifetime import timed_seen
from ssbot.combat.observed_slam import expiry_for_entity

@pytest.fixture
def inputs():
    rng=np.random.default_rng(21);N,T=9,14
    centres=rng.uniform(-1,5,(N,T,2));b=np.stack((centres[:,:,0]-.4,centres[:,:,1]-.4,centres[:,:,0]+.4,centres[:,:,1]+.4),axis=2)
    inv=rng.integers(0,5,(N,T))==0;verts=np.array([[0.,0.],[1.,0.],[1.,1.],[0.,1.],[3.,0.],[4.,0.],[4.,1.],[3.,1.]])
    starts=np.array([0,4,8],np.int64);bb=np.array([[0.,0.,1.,1.],[3.,0.,4.,1.]]);vel=np.array([[0.,0.],[18.,0.]]);tk=np.arange(T)/60;rows=np.arange(N,dtype=np.int64)
    return b,inv,verts,starts,bb,vel,tk,rows,0.

@pytest.mark.parametrize('sweep',[False,True])
def test_infinite_lifetimes_are_exact_existing_kernel(inputs,sweep):
    old=F.seen_contacts_swept(*inputs,1/60,15.) if sweep else F.seen_contacts(*inputs)
    new=timed_seen(*inputs,np.full(2,np.inf),1/60,15.,sweep)
    for a,b in zip(old,new):np.testing.assert_array_equal(a,b)

@pytest.mark.parametrize('sweep',[False,True])
def test_finite_one_never_adds_contact_and_keeps_persistent_other(inputs,sweep):
    old=F.seen_contacts_swept(*inputs,1/60,15.) if sweep else F.seen_contacts(*inputs)
    new=timed_seen(*inputs,np.array([.04,np.inf]),1/60,15.,sweep)
    assert np.all(new[0]<=old[0]);assert np.all(new[1]>=old[1])


def test_short_known_collider_has_only_two_unprotected_contacts(inputs):
    b,inv,v,starts,bb,vel,tk,rows,g=inputs
    b[:]=[-.1,-.1,.5,.5];inv[:]=False;vel[:]=0
    cnt,first=timed_seen(b,inv,v,starts,bb,vel,tk,rows,g,np.array([.04,np.inf]),1/60,15.,False)
    assert (cnt==2).all() and (first==1).all()
    inv[:,:4]=True
    cnt,first=timed_seen(b,inv,v,starts,bb,vel,tk,rows,g,np.array([.04,np.inf]),1/60,15.,False)
    assert not cnt.any() and (first==len(tk)).all()


def context():
    tr=NS(state='Slam 1',t_entry=1.,table=NS(dwell={'Slam 1':(.04,.06)}))
    fc=NS(origin_t=1.02,fc=NS(trackers={1:tr}));e=NS(type_key=NS(v='Song Heavy Sentry'),id=1,fsm=[('Control','Slam 1',.02)])
    fc.rs=NS(trk=NS(now={1:('Song Heavy Sentry',{'hp':10,'hidden':False,'is_dead':False},NS(fam='CC_SLAM',states=['Slam 1']))}))
    raw={'dt':1/60,'fdt':.02,'ts':1.,'fs':1};c=NS(name='Slam Collider 1')
    return e,c,fc,raw


def test_expiry_uses_latest_plus_slack_and_fixed_step():
    e,c,f,r=context();end=expiry_for_entity(e,c,f,r,1/60)
    assert end==pytest.approx(.06+1/60-.02+.02)

@pytest.mark.parametrize('change',['body','other','unknown_clock','overdue','state_mismatch','no_fsm','freeze','missing_origin'])
def test_unknown_and_persistent_cases_keep_infinity(change):
    e,c,f,r=context()
    if change=='body':c.name='Song Heavy Sentry'
    elif change=='other':e.type_key.v='Song Reed'
    elif change=='unknown_clock':r.pop('fdt')
    elif change=='overdue':f.origin_t=1.2;e.fsm=[('Control','Slam 1',.2)]
    elif change=='state_mismatch':f.fc.trackers[1].state='Slam 2'
    elif change=='no_fsm':e.fsm=None
    elif change=='missing_origin':del f.origin_t
    else:r['dt']=0
    assert math.isinf(expiry_for_entity(e,c,f,r,1/60))
@pytest.mark.parametrize('change',['jump','missing_rs','missing_instance','range_state_mismatch'])
def test_cross_family_and_missing_range_identity_remain_infinite(change):
    e,c,f,r=context()
    if change=='jump':f.rs.trk.now[1][2].fam='CC_JUMP'
    elif change=='missing_rs':del f.rs
    elif change=='missing_instance':f.rs.trk.now[1]=('Song Heavy Sentry',{},None)
    else:f.rs.trk.now[1][2].states=['Slam 2']
    assert math.isinf(expiry_for_entity(e,c,f,r,1/60))

@pytest.mark.parametrize('focus,other_type,finite',[(1,'Song Heavy Sentry',True),(2,'Song Heavy Sentry',False),(None,'Song Heavy Sentry',False),(None,'Song Reed',True),(2,'Song Reed',True)])
def test_only_focus_or_unique_clapper_is_finite(focus,other_type,finite):
    e,c,f,r=context();f.rs.focus=focus
    f.rs.trk.now[2]=(other_type,{'hp':10},NS(fam='CC_SLAM',states=['Slam 1']))
    value=expiry_for_entity(e,c,f,r,1/60)
    assert math.isfinite(value)==finite

@pytest.mark.parametrize('bad_focus',[True,1.0,'1'])
def test_malformed_multi_clapper_focus_is_not_an_identity(bad_focus):
    e,c,f,r=context();f.rs.focus=bad_focus
    f.rs.trk.now[2]=('Song Heavy Sentry',{'hp':10},NS(fam='CC_SLAM',states=['Slam 1']))
    assert math.isinf(expiry_for_entity(e,c,f,r,1/60))

@pytest.mark.parametrize('scale',[.5,2.])
def test_scaled_clock_keeps_original_infinite_seen_horizon(scale):
    e,c,f,r=context();r['ts']=scale
    assert math.isinf(expiry_for_entity(e,c,f,r,1/60))
