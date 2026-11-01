import numpy as np
import pytest
from ssbot.combat.scene_field_grid import SceneFieldGrid, SceneFieldCache


def plane(times=(0., .7, 2.3), xs=(0., 2., 5.), ys=(0., 3.)):
    t,y,x=np.meshgrid(times,ys,xs,indexing='ij')
    v=2*x-3*y+5*t+4
    return SceneFieldGrid(times,xs,ys,v,np.ones(v.shape,bool),np.ones(v.shape[1:],int))


def test_nonuniform_event_knots_preserve_a_continuous_affine_field():
    g=plane();p=np.array([[.3,.8,.2],[4.,2.,1.4],[5.,3.,2.3],[0.,0.,0.]])
    v,k=g.query(p)
    assert k.all() and np.allclose(v,2*p[:,0]-3*p[:,1]+5*p[:,2]+4)
    eps=1e-7
    v,k=g.query([[1.,1.,.7-eps],[1.,1.,.7],[1.,1.,.7+eps]])
    assert k.all() and np.allclose(np.diff(v),5*eps,atol=1e-12)


def test_spatial_gradient_guides_nearby_endpoints_without_extra_prediction():
    g=plane();v,k=g.query([[1.,1.,1.],[1.2,1.,1.],[1.4,1.,1.]])
    assert k.all() and np.allclose(np.diff(v),.4)


def test_unknown_is_not_interpolated_into_a_known_reward():
    known=np.array([[[True,False]],[[True,False]]])
    g=SceneFieldGrid([0.,1.],[0.,2.],[0.],np.array([[[3.,np.nan]],[[5.,np.nan]]]),known,[[1,1]])
    v,k=g.query([[0.,0.,.4],[.1,0.,.4],[2.,0.,.4]])
    assert k.tolist()==[True,False,False] and v[0]==pytest.approx(3.8)
    assert np.isnan(v[1:]).all()


def test_different_spatial_regions_and_walls_are_not_blended():
    v=np.array([[[2.,10.,0.]],[[4.,12.,0.]]])
    g=SceneFieldGrid([0.,1.],[0.,2.,4.],[0.],v,np.ones(v.shape,bool),[[1,2,0]])
    values,k=g.query([[0.,0.,.5],[1.,0.,.5],[2.,0.,.5],[3.,0.,.5],[4.,0.,.5]])
    assert k.tolist()==[True,False,True,False,False]
    assert np.allclose(values[[0,2]],[3.,11.])


@pytest.mark.parametrize('p',[[-.1,0.,.5],[5.1,0.,.5],[1.,3.1,.5],[1.,1.,-.1],[1.,1.,2.4],[np.nan,0.,.5],[1.,0.,np.inf]])
def test_no_extrapolation_or_nonfinite_query(p):
    v,k=plane().query([p]);assert not k[0] and np.isnan(v[0])


def test_unknown_time_neighbor_does_not_hide_exact_known_event_knot():
    v=np.array([[[2.]],[[np.nan]],[[6.]]]);g=SceneFieldGrid([0.,1.,2.],[0.],[0.],v,np.isfinite(v),[[1]])
    values,k=g.query([[0.,0.,0.],[0.,0.,.5],[0.,0.,1.],[0.,0.,2.]])
    assert k.tolist()==[True,False,False,True] and values[0]==2 and values[-1]==6


def test_field_owns_read_only_arrays_and_supports_ground_layers_and_empty_queries():
    v=np.array([[[0.,2.]],[[2.,4.]]]);g=SceneFieldGrid([0.,1.],[0.,2.],[4.],v,np.ones(v.shape,bool),[[1,1]])
    v[:]=100
    q,k=g.query([[1.,4.,.5]]);assert k[0] and q[0]==pytest.approx(2.)
    assert all(not getattr(g,n).flags.writeable for n in ['times','xs','ys','values','known','regions'])
    q,k=g.query(np.empty((0,3)));assert not len(q) and not len(k)


def test_invalid_grid_shapes_axes_and_known_values_are_rejected():
    with pytest.raises(ValueError):plane(times=[0.,0.])
    with pytest.raises(ValueError):plane(xs=[0.,np.inf])
    with pytest.raises(ValueError):SceneFieldGrid([0.],[0.],[0.],[[[np.nan]]],[[[True]]],[[1]])
    with pytest.raises(ValueError):SceneFieldGrid([0.],[0.],[0.],[[0.]],[[True]],[[1]])
    with pytest.raises(ValueError):SceneFieldGrid([0.],[0.],[0.],[[[1.]]],[[[True]]],[[1.]])


def test_low_frequency_cache_reuses_absolute_knots_and_refreshes_on_events():
    cache=SceneFieldCache(.4);builds=[]
    def build():
        g=plane();builds.append(g);return g
    first=cache.get(('room',1,'aiming'),.1,build)
    assert all(cache.get(('room',1,'aiming'),t,build) is first for t in [.11,.2,.49])
    assert len(builds)==1 and first.times[1]==.7
    second=cache.get(('room',1,'locked'),.49,build)
    assert second is not first and len(builds)==2
    assert cache.get(('room',1,'locked'),.9,build) is not second and len(builds)==3
    assert cache.get(('room',1,'locked'),.05,build) is not builds[-2] and len(builds)==4
    cache.clear();cache.get(('room',1,'locked'),.05,build);assert len(builds)==5


def test_expired_coverage_and_failed_new_build_never_return_old_layer():
    cache=SceneFieldCache(10.);a=cache.get('a',0.,lambda:plane())
    b=cache.get('a',2.4,lambda:plane(times=[2.4,3.]));assert b is not a
    with pytest.raises(ValueError):cache.get('b',2.5,lambda:plane())
    with pytest.raises(TypeError):cache.get('b',2.5,lambda:None)
    with pytest.raises(ValueError):cache.get('b',np.nan,lambda:b)
    with pytest.raises(ValueError):SceneFieldCache(0.)
