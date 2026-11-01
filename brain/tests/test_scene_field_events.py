import numpy as np
import pytest
from ssbot.combat.scene_field_grid import SceneFieldGrid
from ssbot.combat.scene_field_events import FieldSet, SceneFieldSetCache


def bundle(start=0., end=2.):
    grids={}
    for world,scale in [('nominal',1.),('late',2.)]:
        g=SceneFieldGrid([start,end],[0.,2.],[4.],np.array([[[0.,2.]],[[2.,4.]]])*scale,
                         np.ones((2,1,2),bool),[[1,1]])
        for component in ['egress','room','total']:
            grids[(world,'bounded_hold','ground_run_wait',component)]=g
    return FieldSet(grids,{'identity':'test'},{},4.,.05,('scene',1))


def test_whole_snapshot_builds_once_and_is_pinned_for_all_layers():
    c=SceneFieldSetCache(.25);calls=[]
    def build():
        f=bundle();calls.append(f);return f
    f=c.get(('move',1),0.,build)
    for t in [.01,.1,.249]:
        assert c.get(('move',1),t,build) is f
        for world in ['nominal','late']:
            for component in ['egress','room','total']:
                v,k,reason=f.query([[1.,4.,.6]],world=world,layer='ground_run_wait',hyp='bounded_hold',component=component)
                assert k[0] and reason[0]=='ok'
    assert len(calls)==1
    assert c.get(('move',1),.25,build) is not f
    assert len(calls)==2
    with pytest.raises(TypeError):f.grids['new']=None
    with pytest.raises(ValueError):next(iter(f.grids.values())).values[:]=9


def test_queries_snap_only_the_explicit_ground_tolerance_and_keep_unknown_endpoints():
    f=bundle()
    v,k,r=f.query([[1.,4.03,.6],[1.,4.2,.6],[1.,4.,2.01]],world='nominal',layer='ground_run_wait',hyp='bounded_hold',component='total')
    assert k.tolist()==[True,False,False]
    assert r.tolist()==['ok','air_layer_not_built','outside_or_unknown']
    assert v[0]==pytest.approx(1.6) and np.isnan(v[1:]).all()
    v,k,r=f.query([[1.,4.,.6]],world='nominal',layer='air',hyp='bounded_hold',component='total')
    assert not k[0] and r[0]=='component_or_layer_unavailable'


def test_cache_rebuilds_on_lock_change_clock_reset_expiry_or_clear():
    c=SceneFieldSetCache(20.);a=c.get(('lock',1),.1,lambda:bundle())
    b=c.get(('lock',2),.2,lambda:bundle());assert b is not a
    assert c.get(('lock',2),.05,lambda:bundle()) is not b
    newer=c.get(('lock',2),2.01,lambda:bundle(2.,4.));assert newer is not b
    c.clear();assert c.get(('lock',2),2.02,lambda:bundle(2.,4.)) is not newer


def test_failed_new_build_does_not_publish_partial_or_wrong_event():
    c=SceneFieldSetCache(10.);a=c.get('a',0.,lambda:bundle())
    def incomplete():
        raise RuntimeError('not finished')
    with pytest.raises(RuntimeError):c.get('b',.1,incomplete)
    assert c.get('a',.1,lambda:None) is a
    with pytest.raises(TypeError):c.get('b',.1,lambda:{'status':'insufficient_coverage'})
    with pytest.raises(ValueError):c.get('b',.1,lambda:bundle(1.,2.))
    with pytest.raises(ValueError):c.get(None,.1,lambda:bundle())
    with pytest.raises(ValueError):c.get('b',np.nan,lambda:bundle())
    with pytest.raises(ValueError):SceneFieldSetCache(0.)


@pytest.mark.parametrize('mask',[[[[1]]],[[[np.nan]]],[[[0.]]]])
def test_nonboolean_coverage_masks_are_rejected(mask):
    with pytest.raises(ValueError,match='boolean mask'):
        SceneFieldGrid([0.],[0.],[0.],[[[0.]]],mask,[[1]])
