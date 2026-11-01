"""Integer-time B2 continuation checks: keep closing pulses, not sparse-bracket ghosts."""
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import observed_slam as O
from ssbot.combat import forum_v2 as V
from ssbot.combat.attack_range import FT
from ssbot.combat.knife_chain_geometry import B2Geometry


def setup_geometry(monkeypatch, *, pulse=36, owner=7, delayed=False, shift=0):
    instance=NS(fam="CC_SLAM")
    trk=NS(now={7:(O.CLAPPER,{},instance),8:(O.CLAPPER,{},NS(fam="CC_SLAM"))},orphan_hazards={})
    cv=V.Canvas(cell=.1,box=(0.,0.,20.,10.))
    row,col,ok=cv.index(np.array([10.]),np.array([5.]));assert ok[0]
    def build(samples,k_shift=0):
        out=V.LayerSupport(cv,samples,k_shift);out.trk=trk;out.margin_mode="focus";out.focus=7;out.focus_arg=7
        for si,k in enumerate(samples):
            if k!=pulse:continue
            tile=np.ones((1,1),bool);out.add(si,owner,tile,int(col[0]),int(row[0]))
            if delayed:out.haz_raw[owner]=[(si,tile,int(col[0]),int(row[0]),0.,None)]
        return out
    rs=build((0,36,42,62),shift);calls=[]
    def fresh(tracker,**kwargs):
        assert tracker is trk
        calls.append(kwargs)
        return build(kwargs["samples"],kwargs.get("k_shift",0))
    monkeypatch.setattr(V.RangeSupport,"build",fresh)
    geo=B2Geometry(NS(rs=rs),100,NS(target_iid=7),instance)
    def path(first=37,length=3,stage="continuation"):
        return NS(origin=100+first,through=100+first+length,stage=stage,
            box=np.tile([9.8,4.7,10.2,5.3],(length+1,1)),commands=np.zeros(length,np.int64),
            flags=np.zeros(length+1,np.int64),check_flags=np.zeros(length+1,np.int64))
    return geo,rs,calls,path


def test_expired_left_pulse_does_not_fill_the_continuation_bracket(monkeypatch):
    monkeypatch.setattr(O,"ENABLED",True)
    geo,rs,calls,path=setup_geometry(monkeypatch,pulse=36)
    before=rs.stack.copy()
    assert not geo.scan(path()).contacts
    assert calls[0]["samples"]==tuple(range(37,41))
    np.testing.assert_array_equal(rs.stack,before)
    assert rs.samples==(0,36,42,62)


@pytest.mark.parametrize("pulse",[37,39,40])
def test_exact_continuation_keeps_closing_and_between_knot_pulses(monkeypatch,pulse):
    monkeypatch.setattr(O,"ENABLED",True)
    geo,rs,calls,path=setup_geometry(monkeypatch,pulse=pulse)
    contacts=geo.scan(path()).contacts
    assert [(c.frame,c.owner_iid,c.kind) for c in contacts]==[(100+pulse,7,"move")]


@pytest.mark.parametrize("owner,delayed,kind",[(7,True,"delayed"),(8,True,"delayed"),(8,False,"move")])
def test_dense_continuation_preserves_all_owners_and_delayed_hazards(monkeypatch,owner,delayed,kind):
    monkeypatch.setattr(O,"ENABLED",True)
    geo,rs,calls,path=setup_geometry(monkeypatch,pulse=40,owner=owner,delayed=delayed)
    assert [(c.frame,c.owner_iid,c.kind) for c in geo.scan(path()).contacts]==[(140,owner,kind)]


def test_same_tick_same_window_reuses_raster_and_owner_cache(monkeypatch):
    monkeypatch.setattr(O,"ENABLED",True)
    geo,rs,calls,path=setup_geometry(monkeypatch,pulse=40)
    a=geo.scan(path());b=geo.scan(path())
    assert a.contacts==b.contacts and len(calls)==1
    assert calls[0]["canvas"] is rs.cv and calls[0]["focus"]==7
    # A different proposal/tick never borrows this object's mutable cache.
    other=B2Geometry(geo.forecast,geo.origin,geo.move,geo.instance)
    other.scan(path());assert len(calls)==2


def test_dense_window_rebases_a_shifted_cached_support(monkeypatch):
    monkeypatch.setattr(O,"ENABLED",True)
    geo,rs,calls,path=setup_geometry(monkeypatch,pulse=40,shift=-1)
    assert [c.frame for c in geo.scan(path()).contacts]==[140]
    assert calls[0].get("k_shift",0)==0
    assert calls[0]["samples"]==tuple(range(37,41))


def test_model_off_keeps_the_original_continuation_query(monkeypatch):
    monkeypatch.setattr(O,"ENABLED",False)
    geo,rs,calls,path=setup_geometry(monkeypatch,pulse=36)
    assert [c.frame for c in geo.scan(path()).contacts]==[137,138,139,140]
    assert not calls


def test_current_strike_keeps_original_query_and_does_not_gain_admission(monkeypatch):
    monkeypatch.setattr(O,"ENABLED",True)
    geo,rs,calls,path=setup_geometry(monkeypatch,pulse=36)
    contacts=geo.scan(path(stage="commitment")).contacts
    assert [c.frame for c in contacts]==[137,138,139,140]
    assert not calls
