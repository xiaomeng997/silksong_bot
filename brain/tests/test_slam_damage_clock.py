"""CC_SLAM damage-clock closure: previous local shape, unchanged current root."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import attack_range as A, observed_slam as O


def table(fam="CC_SLAM",empty=False,gated=False):
    shapes=[np.ones((1,1),bool),np.ones((1,4),bool),np.zeros((0,0),bool) if empty else np.ones((1,1),bool)]
    tp=A.Template(nb=3,shape=shapes,origin=np.zeros((3,2),np.int64),disp=np.array([[0.,0.],[1.,0.],[2.,0.]]))
    if gated:
        tp.sst=[{"Slam Antic":(shapes[0],0,0)},{"Slam 2":(shapes[1],0,0)},{"Slam Recover":(shapes[2],0,0)}]
        tp.order={"Slam Antic":0,"Slam 2":1,"Slam Recover":2}
    return A.RangeTable(A.SPECS[O.CLAPPER],{(fam,"main"):tp},cell=1.),tp


def cells(m):
    return {(int(c)+m.ix0,int(r)+m.iy0) for r,c in zip(*np.nonzero(m.m))}


@pytest.mark.parametrize("facing",[1,-1])
def test_previous_local_shape_is_at_current_root(monkeypatch,facing):
    tab,tp=table();monkeypatch.setattr(O,"ENABLED",True)
    got=tab.place("CC_SLAM","main",2,(8.,5.),facing)
    expected=A.place_shape(np.ones((1,4),bool),0,0,8.+2*facing,5.,facing,1.)
    assert cells(got)==cells(expected)
    # Carrying the old WORLD geometry would leave the old root in place.
    wrong=A.place_shape(tp.shape[1],0,0,8.+facing,5.,facing,1.)
    assert cells(got)!=cells(wrong)


def test_default_off_keeps_the_original_shape(monkeypatch):
    tab,tp=table();monkeypatch.setattr(O,"ENABLED",False)
    got=tab.place("CC_SLAM","main",2,(8.,5.),1)
    assert cells(got)==cells(A.place_shape(tp.shape[2],0,0,10.,5.,1,1.))


def test_closing_frame_can_have_an_empty_current_shape(monkeypatch):
    tab,tp=table(empty=True);monkeypatch.setattr(O,"ENABLED",True)
    assert cells(tab.place("CC_SLAM","main",2,(8.,5.),1))==cells(A.place_shape(tp.shape[1],0,0,10.,5.,1,1.))


@pytest.mark.parametrize("b",[0,3,30])
def test_previous_bin_is_clamped_independently_without_wrap_or_end_ghost(monkeypatch,b):
    tab,tp=table();monkeypatch.setattr(O,"ENABLED",True)
    got=tab.place("CC_SLAM","main",b,(8.,5.),1)
    assert len(cells(got))==1


def test_current_state_gate_cannot_erase_the_previous_closing_hammer(monkeypatch):
    tab,tp=table(gated=True);monkeypatch.setattr(O,"ENABLED",True)
    got=tab.place("CC_SLAM","main",2,(8.,5.),1,now=(10.,5.),b_now=2,st_now="Slam Recover")
    assert len(cells(got))==4


def test_other_family_does_not_acquire_a_clock_layer(monkeypatch):
    tab,tp=table(fam="CC_CAST");monkeypatch.setattr(O,"ENABLED",True)
    assert len(cells(tab.place("CC_CAST","main",2,(8.,5.),1)))==1


def test_reanchored_and_observed_stopped_root_stays_current(monkeypatch):
    tab,tp=table();monkeypatch.setattr(O,"ENABLED",True)
    inst=A.Inst("CC_SLAM",0.,8.,5.,1,0.,states=["Slam 2"])
    row=O.Motion(inst,100,100,20.,1,True,True,True,99)
    moving=tab.place("CC_SLAM","main",2,(8.,5.),1,now=(20.,5.),b_now=1)
    stopped=tab.place("CC_SLAM","main",2,(8.,5.),1,now=(20.,5.),b_now=1,ctx={"observed_motion":(inst,row)})
    assert moving.bbox(1.)==(21.,5.,25.,6.)
    assert stopped.bbox(1.)==(20.,5.,24.,6.)


def test_source_template_is_unchanged_and_original_support_is_preserved(monkeypatch):
    tab,tp=table(gated=True);before=[x.copy() for x in tp.shape]
    for b in range(8):
        monkeypatch.setattr(O,"ENABLED",False);old=tab.place("CC_SLAM","main",b,(8.,5.),1,st_now="Slam Recover",b_now=2)
        monkeypatch.setattr(O,"ENABLED",True);new=tab.place("CC_SLAM","main",b,(8.,5.),1,st_now="Slam Recover",b_now=2)
        assert cells(old)<=cells(new)
    for a,b in zip(before,tp.shape):np.testing.assert_array_equal(a,b)


def test_raw_owner_and_b2_continuation_use_the_same_clock_layer(monkeypatch):
    from ssbot.combat import forum_v2 as V
    from ssbot.combat.knife_chain_geometry import B2Geometry
    tab,tp=table();monkeypatch.setattr(O,"ENABLED",True)
    # RangeSupport accepts the real fine lattice, not an upsample from the
    # one-unit synthetic masks used in the placement-only tests above.
    tab.cell=A.CELL;tp.shape=[np.repeat(np.repeat(sh,20,axis=0),20,axis=1) for sh in tp.shape]
    tr=A.RangeTracker({O.CLAPPER:tab});tr.T=2*A.FT
    inst=A.Inst("CC_SLAM",0.,20.,5.,1,0.,states=["Slam Recover"])
    ent={"pos":[22.,5.,0.],"vel":[0.,0.],"hp":10,"flipX":True,"fsms":[{"name":"Control","state":"Slam Recover","t":0.}]}
    tr.now={1:(O.CLAPPER,ent,inst)}
    rs=V.RangeSupport.build(tr,focus=1,margin_mode="zero")
    x=np.array([25.5]);y=np.array([5.5]);t=np.array([0.])
    assert rs.occupied(x,y,t)[0] and rs.occupied_only(x,y,t,{1})[0]
    assert not rs.occupied_without(x,y,t,{1})[0]
    move=NS(target_iid=1);g=B2Geometry(NS(rs=rs),100,move,inst)
    path=NS(origin=100,through=100,box=np.array([[25.25,4.5,25.75,6.5]]),flags=np.zeros(1,np.int64),check_flags=np.zeros(1,np.int64),stage="continuation",commands=np.zeros(1,np.int64))
    assert g.scan(path,0).contacts


def test_model_revision_changes_for_clock_semantics():
    assert O.revision_fields()["observed_slam_revision"]==2
