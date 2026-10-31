"""Pure dilation equality, mutation isolation and bounded proposal lifetime."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
import numpy as np
import pytest
from ssbot.combat import forum_v2 as fv
from ssbot.combat.knife_chain_raster_cache import exact_dilation_scope,current_dilation_cache,ExactDilationCache


def parts():
    a=np.zeros((5,8),bool);a[1:4,2:6]=True
    return [(a,-7,11),(np.eye(4,dtype=bool),-2,13)]


def same(a,b):
    assert a[1:]==b[1:] and a[0].dtype==b[0].dtype
    assert np.array_equal(a[0],b[0])


@pytest.mark.parametrize("margin,cell",[(0.,.2),(.5,.2),(1.25,.2),(.5,.1)])
def test_identical_content_reuse_matches_original_exactly(margin,cell):
    ps=parts();expected=fv._dilate_group_uncached(ps,margin,cell)
    with exact_dilation_scope() as cache:
        first=fv.dilate_group(ps,margin,cell)
        second=fv.dilate_group([(a.copy(),x,y) for a,x,y in ps],margin,cell)
        same(first,expected);same(second,expected)
        assert cache.misses==1 and cache.hits==1
        assert first[0] is not second[0] and not np.shares_memory(first[0],second[0])
    assert current_dilation_cache() is None and not cache.active and not cache.entries


def test_mutable_input_pixels_positions_margins_and_cell_cannot_alias():
    ps=parts()
    with exact_dilation_scope() as cache:
        same(fv.dilate_group(ps,.5),fv._dilate_group_uncached(ps,.5))
        ps[0][0][0,0]=True
        same(fv.dilate_group(ps,.5),fv._dilate_group_uncached(ps,.5))
        moved=[(a,x+1,y) for a,x,y in ps]
        same(fv.dilate_group(moved,.5),fv._dilate_group_uncached(moved,.5))
        same(fv.dilate_group(moved,.75),fv._dilate_group_uncached(moved,.75))
        same(fv.dilate_group(moved,.75,.05),fv._dilate_group_uncached(moved,.75,.05))
        assert cache.misses==5 and cache.hits==0


def test_output_mutation_never_changes_future_hits():
    ps=parts();expected=fv._dilate_group_uncached(ps,.5)
    with exact_dilation_scope() as cache:
        a=fv.dilate_group(ps,.5);a[0][:]=False
        b=fv.dilate_group(ps,.5);same(b,expected);b[0][:]=False
        same(fv.dilate_group(ps,.5),expected)
        assert cache.hits==2


def test_kernel_globals_are_part_of_exact_key(monkeypatch):
    ps=parts()
    with exact_dilation_scope() as cache:
        fv.dilate_group(ps,.5)
        monkeypatch.setattr(fv,"HB_HX",fv.HB_HX+.25)
        same(fv.dilate_group(ps,.5),fv._dilate_group_uncached(ps,.5))
        assert cache.misses==2


@pytest.mark.parametrize("adapt",["kernel","compute"])
def test_adapter_overrides_keep_their_original_behavior(monkeypatch,adapt):
    ps=parts();calls=[]
    if adapt=="kernel":
        old=fv.box_kernel
        def box(*a,**kw):calls.append(None);return old(*a,**kw)
        monkeypatch.setattr(fv,"box_kernel",box)
    else:
        old=fv._dilate_group_uncached
        def compute(*a,**kw):calls.append(None);return old(*a,**kw)
        monkeypatch.setattr(fv,"_dilate_group_uncached",compute)
    with exact_dilation_scope() as cache:
        fv.dilate_group(ps,.5);fv.dilate_group(ps,.5)
        assert len(calls)==2 and not cache.entries and not cache.hits


def test_generator_is_materialized_once_and_empty_groups_remain_equal():
    ps=parts()
    with exact_dilation_scope() as cache:
        same(fv.dilate_group((p for p in ps),.5),fv._dilate_group_uncached(ps,.5))
        fv.dilate_group(ps,.5)
        same(fv.dilate_group([],.5),fv._dilate_group_uncached([],.5))
        assert cache.hits==1


def test_nested_scope_joins_parent_and_new_proposal_cannot_reuse_it():
    ps=parts()
    with exact_dilation_scope() as outer:
        fv.dilate_group(ps,.5)
        with exact_dilation_scope() as inner:
            assert inner is outer;fv.dilate_group(ps,.5)
        assert outer.active and outer.hits==1
    with exact_dilation_scope() as next_tick:
        assert next_tick is not outer;fv.dilate_group(ps,.5)
        assert next_tick.misses==1 and not next_tick.hits


def test_exception_releases_all_entries_and_thread_context_is_private():
    with pytest.raises(RuntimeError,match="test failure"):
        with exact_dilation_scope() as cache:
            fv.dilate_group(parts(),.5)
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(current_dilation_cache).result() is None
            raise RuntimeError("test failure")
    assert current_dilation_cache() is None and not cache.active and not cache.entries


def test_unknown_representation_falls_back_and_original_exception_propagates():
    cache=ExactDilationCache();calls=[]
    def compute(ps,m,cell):calls.append(None);return np.ones((1,1),bool),0,0
    ps=[(np.ones((1,1),bool),object(),0)]
    cache.apply(ps,.5,.2,compute,());cache.apply(ps,.5,.2,compute,())
    assert len(calls)==2 and cache.uncacheable==2 and not cache.entries
    def bad(*a):raise RuntimeError("original compute failed")
    with pytest.raises(RuntimeError,match="original compute failed"):
        cache.apply(parts(),.5,.2,bad,())


def test_native_proposal_clears_scope_and_keeps_original_error(monkeypatch):
    from ssbot.combat.knife_chain_b2 import NativeChainB2
    from tests.test_knife_chain_b2 import runner
    n=NativeChainB2(runner_factory=runner,probe_ref="raster-scope")
    def work(*a):
        fv.dilate_group(parts(),.5);fv.dilate_group(parts(),.5)
        raise RuntimeError("original proposal failure")
    monkeypatch.setattr(n,"_propose",work)
    with pytest.raises(RuntimeError,match="original proposal failure"):
        n.propose(None,None,None,None,None,None,None,None)
    assert current_dilation_cache() is None and n._proposal_started is None


def test_array_subclass_with_different_view_keeps_original_behavior():
    class CustomView(np.ndarray):
        def view(self,*args,**kwargs):
            return np.zeros(self.shape,dtype=np.uint8)
    ps=parts()
    special=[(a.view(CustomView),x,y) for a,x,y in ps]
    assert all(np.array_equal(a,b) for (a,_,_),(b,_,_) in zip(ps,special))
    with exact_dilation_scope() as cache:
        fv.dilate_group(ps,.5)
        same(fv.dilate_group(special,.5),fv._dilate_group_uncached(special,.5))
        assert cache.misses==1 and cache.uncacheable==1 and not cache.hits


@pytest.mark.parametrize("slot",["margin","cell","coordinate","context"])
def test_scalar_slots_with_array_representation_keep_original_compute(slot):
    cache=ExactDilationCache();ps=parts();m=.5;cell=.1;context=();calls=[]
    if slot=="margin":m=np.asarray(.5)
    if slot=="cell":cell=np.asarray(.1)
    if slot=="coordinate":ps=[(a,np.asarray(x),y) for a,x,y in ps]
    if slot=="context":context=(np.asarray(.5),)
    def compute(*args):calls.append(None);return np.ones((1,1),bool),0,0
    cache.apply(ps,m,cell,compute,context);cache.apply(ps,m,cell,compute,context)
    assert len(calls)==2 and cache.uncacheable==2 and not cache.entries
