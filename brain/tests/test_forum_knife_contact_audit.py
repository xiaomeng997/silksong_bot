from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.tools.forum_knife_contact_audit import contact_gate,real_down_hits,predict,clock_lanes,contact_interval


def test_contact_gate_keeps_every_outcome_and_original_boundaries():
    sw=np.array([43,43]);cc=np.array([48,49]);controls=np.array([28,30])
    assert contact_gate(sw,cc,[True,True],controls,37,80,14)
    assert not contact_gate(sw,cc,[True,False],controls,37,80,14)
    assert not contact_gate(sw,[37,49],[True,True],controls,37,80,14)
    assert not contact_gate(sw,[48,66],[True,True],controls,37,80,14)
    assert not contact_gate(sw,cc,[True,True],[28,34],37,80,14)
    with pytest.raises(ValueError):contact_gate([],[],[],[],37,80,14)


def test_real_contact_uses_event_frame_target_and_down_hit_not_damage_call():
    frames=[dict(f=101,ev=[dict(k="hit",f=100,d=dict(ent=7,src="Down Slash")),
                            dict(k="hit",f=100,d=dict(ent=8,src="Down Slash")),
                            dict(k="damage",f=100,d=dict(ent=7,src="Down Slash")),
                            dict(k="hit",f=100,d=dict(ent=7,src="Harpoon Damager"))])]
    assert real_down_hits(frames,7)==[100]


def test_predictor_cannot_be_fed_future_states():
    with pytest.raises(ValueError,match="history must stop"):
        predict([dict(f=101)],100,None,7,None,None,None,None,None,None)


def test_clock_expansion_preserves_nominal_and_exposes_every_existing_lane():
    from ssbot.knowledge import kinematics as km
    params=km.HeroParams();st=km.initial_state(params,30.,12.,ground=False,alpha=.5)
    st[km.ALO]=.1;st[km.AHI]=.9
    commands=np.zeros(24,np.int64)
    nominal=km.rollout(st,commands[None],params,variants="bounds",threads=1)
    base=SimpleNamespace(hooks=[object()],control_frames=np.array([0]),control_states={0:st},
                         box=nominal.box,flags=nominal.flags,mode=nominal.mode)
    expanded=clock_lanes(base,commands,params,None)
    assert expanded.clock_lanes==[x.name for x in km.BOUNDS]
    assert np.array_equal(expanded.box[0],nominal.box[0])
    assert expanded.box.shape==(9,25,4)
    assert np.unique(expanded.box,axis=0).shape[0]>1


def test_contact_interval_keeps_early_possible_pogo_separate_from_late_guarantee():
    from ssbot.combat.forum_planner import _shapes
    from ssbot.knowledge import kinematics as km
    planner=SimpleNamespace(shapes=_shapes("Wanderer"))
    length=20;commands=np.zeros(length,np.int64)
    commands[1:3]=km.B_DOWN|km.B_ATTACK
    flags=np.zeros((1,length+1),np.int64);flags[:,2:12]=km.F_ATTACKING
    box=np.tile([29.5,8.,30.5,9.],(1,length+1,1))
    # A descending slash first brushes the outer envelope, then penetrates
    # the inner body far enough to survive every permitted hero residual.
    box[0,:,1::2]-=np.arange(length+1)[:,None]*.25
    ro=SimpleNamespace(box=box,flags=flags,mode=np.zeros_like(flags),hooks=[object()])
    body=np.tile([29.,3.,31.,5.],(length+1,1))
    sw,early,late,robust=contact_interval(planner,ro,commands,1,body,body)
    assert robust.tolist()==[True]
    assert sw.tolist()==[2]
    assert 2<early[0]<late[0]<12
    far=body+np.array([100.,0.,100.,0.])
    assert not contact_interval(planner,ro,commands,1,far,far)[3].any()
    with pytest.raises(ValueError,match="invalid contact bounds"):
        contact_interval(planner,ro,commands,1,body,body,residual=-.1)


def test_one_missing_shift_has_no_fabricated_guaranteed_contact(monkeypatch):
    from ssbot.combat.forum_planner import ForumPlanner
    count=0
    def detector(*args,**kwargs):
        nonlocal count
        count+=1
        # One inner-envelope temporal alternative has no guaranteed hit.
        cc=-1 if count==2 else 7
        return np.array([2]),np.array([cc]),np.array([0]),np.array([cc>=0])
    monkeypatch.setattr(ForumPlanner,"_ds_hits",detector)
    planner=SimpleNamespace(shapes=(None,None,None,np.array([[0,1]]*4)))
    ro=SimpleNamespace(hooks=[object()])
    body=np.tile([0.,0.,2.,2.],(13,1))
    _,first,last,robust=contact_interval(planner,ro,np.zeros(12,np.int64),1,body,body)
    assert first.tolist()==[7] and last.tolist()==[-1] and robust.tolist()==[False]
