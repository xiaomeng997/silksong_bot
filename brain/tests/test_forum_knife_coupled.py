from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat import forum_knife_coupled as coupled,forum_v2 as v2,attack_range as ar


def test_clock_uses_one_coherent_duration_family_and_one_common_shift():
    obs=SimpleNamespace(st="Slam Antic",j=1)
    clock=coupled.world_clock(obs,(3,2,2,3,2),12)
    assert clock[0]==("Slam Antic",1) and clock[2]==("Slam 0",0)
    assert clock[4]==("Slam 1",0) and clock[6]==("Slam 2",0)
    assert clock[9]==("Slam Recover",0) and clock[11] is None
    shifted=coupled.world_clock(obs,(3,2,2,3,2),12,2)
    assert shifted[:-2]==clock[2:]
    with pytest.raises(ValueError,match="world clock"):
        coupled.world_clock(obs,(1,2,2,3,2),12)


@pytest.fixture
def support():
    cv=v2.Canvas(cell=.25,box=(0,0,16,4));samples=(0,2,6,10)
    masks={name:(np.ones((1,1),bool),4+8*i,4) for i,name in enumerate(coupled.STATES)}
    tp=SimpleNamespace(sst=[masks]);tab=SimpleNamespace(cell=.25,templates={("CC_SLAM","main"):tp})
    core=ar.Mask(np.ones((1,1),bool),12,4);haz=ar.Mask(np.ones((1,1),bool),44,4)
    def estimate(iid,k):return SimpleNamespace(raw=ar.union([core,haz]),core=core,haz=haz)
    inst=SimpleNamespace(fam="CC_SLAM",s=1)
    trk=SimpleNamespace(now={7:(v2.CLAPPER,{},inst)},tables={v2.CLAPPER:tab},estimate=estimate)
    rs=v2.RangeSupport(cv,samples,0);rs.trk=trk;rs.focus=7
    rs.bombs=np.array([[6.,6.,2.,.5,0.,2.]])
    for si,k in enumerate(samples):
        c,x,y=v2.coarse(estimate(7,k).raw,.25,cv.cell)
        rs.add_raw(si,7,c,x,y,rs.m_of(7,v2.CLAPPER,k),.5)
        rs.add_raw(si,9,np.ones((1,1),bool),52,4,.25,.75)
    rs.finish()
    f=v2.V2Forecast(SimpleNamespace(fc=None),rs)
    obs=SimpleNamespace(st="Slam Antic",j=0,iid=7,face=1)
    return f,obs


def test_same_shift_moves_target_clock_but_preserves_other_owner_and_hazard(support):
    f,obs=support;roots=np.zeros((11,2));before=f.rs.stack.copy()
    out=coupled.conditioned_slam(f,obs,(2,2,2,2,2),1,roots)
    t=np.arange(5)/60;x=np.full((1,5),3.1);y=np.full((1,5),1.1)
    assert out.rs.occupied_only(x,y,t,[7]).tolist()==[[False,True,True,True,False]]
    assert out.rs.bombs is f.rs.bombs and np.array_equal(f.rs.stack,before)
    bx=np.array([[6.,6.,6.]]);by=np.array([[2.,2.,2.]]);bt=np.arange(3)/60
    assert out.rs.occupied_only(bx,by,bt,[6]).all()
    assert np.array_equal(out.rs.occupied_esc(bx,by,bt),f.rs.occupied_esc(bx,by,bt))
    xx,yy=np.meshgrid(np.arange(.125,16,.25),np.arange(.125,4,.25))
    for k in range(11):
        tk=np.full(xx.shape,k/60)
        assert np.array_equal(out.rs.occupied_only(xx,yy,tk,[9]),f.rs.occupied_only(xx,yy,tk,[9]))
        assert out.rs.occupied_only(np.array([[11.1]]),np.array([[1.1]]),np.array([k/60]),[7]).all()


def test_unknown_post_slam_keeps_original_target_core(support):
    f,obs=support
    out=coupled.conditioned_slam(f,obs,(2,2,2,2,2),0,np.zeros((11,2)))
    assert out.rs.occupied_only(np.array([[3.1]]),np.array([[1.1]]),np.array([10/60]),[7]).all()


def test_unknown_target_piece_and_origin_shift_cannot_silently_drop_danger(support):
    f,obs=support;f.rs.raw[0].append(f.rs.raw[0][0])
    with pytest.raises(ValueError,match="unrecognized target"):
        coupled.conditioned_slam(f,obs,(2,2,2,2,2),0,np.zeros((11,2)))
    f.rs.k_shift=-1
    with pytest.raises(ValueError,match="support/origin"):
        coupled.conditioned_slam(f,obs,(2,2,2,2,2),0,np.zeros((11,2)))


def test_paired_contact_bounds_preserve_the_uncoupled_interval_when_reunited():
    from ssbot.combat.forum_planner import ForumPlanner,_shapes
    from ssbot.tools.forum_knife_contact_audit import contact_interval
    from ssbot.knowledge import kinematics as km
    planner=SimpleNamespace(shapes=_shapes("Wanderer"))
    planner._ds_hits=lambda *args:ForumPlanner._ds_hits(planner,*args)
    length=20;commands=np.zeros(length,np.int64)
    commands[1:3]=km.B_DOWN|km.B_ATTACK
    flags=np.zeros((1,length+1),np.int64);flags[:,2:12]=km.F_ATTACKING
    boxes=np.tile([29.5,8.,30.5,9.],(1,length+1,1))
    boxes[0,:,1::2]-=np.arange(length+1)[:,None]*.25
    ro=SimpleNamespace(box=boxes,flags=flags,mode=np.zeros_like(flags),hooks=[object()])
    body=np.tile([29.,3.,31.,5.],(length+1,1))
    sw,early,late,robust=contact_interval(planner,ro,commands,1,body,body)
    bounds=[coupled.contact_bounds(planner,ro,commands,1,body,body,shift) for shift in (-2,-1,0,1,2)]
    assert robust.all() and all(x[3].all() for x in bounds)
    assert np.array_equal(early,np.min([x[1] for x in bounds],axis=0))
    assert np.array_equal(late,np.max([x[2] for x in bounds],axis=0))
    assert all(np.array_equal(sw,x[0]) for x in bounds)
    unknown=body.copy();unknown[3:10]=np.nan
    assert not coupled.contact_bounds(planner,ro,commands,1,unknown,unknown)[3].any()
