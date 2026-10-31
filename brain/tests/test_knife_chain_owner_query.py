"""Same-tick raster reuse must retain fresh spatial/time/bomb queries."""
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat.knife_chain_geometry import B2Geometry
from tests.test_forum_v2 import _support_with


def geo(rs):
    return B2Geometry(SimpleNamespace(rs=rs),100,SimpleNamespace(target_iid=100),None)


@pytest.mark.parametrize("owner",[100,101,999])
def test_same_owner_raster_queries_keep_points_time_and_filter(owner,monkeypatch):
    rs=_support_with([(24.,4.,26.,6.),(34.,4.,36.,6.)],samples=(0,4,8))
    original=rs._stack_of;calls=[]
    def counted(keep):
        calls.append(1);return original(keep)
    monkeypatch.setattr(rs,"_stack_of",counted)
    g=geo(rs)
    for shift in [0.,1.,-1.]:
        x=np.array([[25.,35.,45.,np.nan]])+shift;y=np.full(x.shape,5.)
        t=np.array([0.,2.,8.,4.])/60
        expected=rs.occupied_only(x,y,t,{owner});calls.clear()
        got=g._owner_occupancy(rs,x,y,t,owner)
        np.testing.assert_array_equal(got,expected)
        assert len(calls)==(1 if shift==0. else 0)


def test_new_proposal_or_support_does_not_reuse_owner_raster():
    rs=_support_with([(24.,4.,26.,6.)],samples=(0,4,8))
    x=np.array([[25.]]);y=np.array([[5.]]);t=np.array([0.])
    a=geo(rs);assert a._owner_occupancy(rs,x,y,t,100)[0,0]
    # Actual next-tick body/hazard changes require a fresh query group.
    other=_support_with([(34.,4.,36.,6.)],samples=(0,4,8))
    assert not a._owner_occupancy(other,x,y,t,100)[0,0]
    assert not geo(other)._owner_occupancy(other,x,y,t,100)[0,0]


def test_bomb_owner_filter_and_live_time_are_still_queried(monkeypatch):
    rs=_support_with([],samples=(0,4,8));calls=[]
    def bombs(x,y,t,owners):
        calls.append((tuple(t),frozenset(owners)))
        return np.broadcast_to((np.asarray(t)>=.05)&(100 in owners),np.asarray(x).shape)
    monkeypatch.setattr(rs,"bomb_occ",bombs)
    g=geo(rs);x=np.array([[25.,25.]]);y=np.full(x.shape,5.)
    for owner in [100,101]:
        for t in [np.array([0.,.1]),np.array([.2,0.])]:
            np.testing.assert_array_equal(g._owner_occupancy(rs,x,y,t,owner),rs.occupied_only(x,y,t,{owner}))
    assert len(calls)==8


def test_adapter_overrides_keep_original_query_semantics():
    calls=[]
    def query(x,y,t,owners):
        calls.append(1);return np.full(np.asarray(x).shape,len(calls)%2==0)
    rs=SimpleNamespace(occupied_only=query);g=geo(rs)
    x=np.array([[25.]]);y=x;t=np.array([0.])
    assert not g._owner_occupancy(rs,x,y,t,100)[0,0]
    assert g._owner_occupancy(rs,x,y,t,100)[0,0]
    assert not g._owners
