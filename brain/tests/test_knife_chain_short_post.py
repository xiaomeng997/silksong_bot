"""Short checkpoints retain real handback semantics and exact model evolution."""
from dataclasses import replace
import numpy as np
import pytest
from ssbot.knowledge import kinematics as km
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.knife_chain_nominal import compile_path,finish_post,NominalProfile
from ssbot.combat.knife_chain_step import hold_one
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.knife_chain_commitment import FullContinuationScan
from tests.test_knife_chain_b2 import params,terrain,preview
from tests.test_knife_chain_commitment import option,assess,no_full,scan


def test_one_frame_hold_matches_original_for_queues_and_conflicts():
    rng=np.random.default_rng(312)
    a=km.HoldState.idle(1);b=a.copy()
    for cmd in rng.integers(0,1<<12,300):
        got,a=hold_one(int(cmd),a)
        expected,b=hold_filter_jit(np.array([[cmd]],np.int64),b)
        assert got==expected[0,0]
        for name in ("latched","desired","pending","age"):
            np.testing.assert_array_equal(getattr(a,name),getattr(b,name))


@pytest.mark.parametrize("kind",["left_landing","right_landing","dash_out"])
def test_short_checkpoint_resumes_without_changing_program_or_physics(params,terrain,kind):
    _,p,raw,sim=preview(params,terrain)
    parent=compile_path(p.draft,raw,sim,0.,stage="commitment",first_mask=p.mask)
    bs=ChainSim(parent.states[:,-1],np.array([parent.queued_next],np.int64),parent.hold_end,params,terrain,parent.through,parent.through)
    args=dict(stage="continuation",first_mask=0,branch=kind,known_press=parent.press_frame)
    full=compile_path(parent.runner_end,parent.raw_end,bs,float(parent.game[-1]),**args)
    short=compile_path(parent.runner_end,parent.raw_end,bs,float(parent.game[-1]),stop_after=12,**args)
    assert short.end=="short" and len(short.commands)>=12
    resumed=finish_post(short,params,terrain)
    assert resumed.end=="handback" and resumed.through==full.through
    for name in ("commands","latched","flags","check_flags"):
        np.testing.assert_array_equal(getattr(resumed,name),getattr(full,name))
    for name in ("states","box","pos","game"):
        np.testing.assert_allclose(getattr(resumed,name),getattr(full,name),atol=1e-12,rtol=0)
    assert resumed.first_draft.run.lid==full.first_draft.run.lid


def test_unknown_handback_is_valid_for_two_short_types_only():
    opts=[replace(option("l","left_landing"),handback_frame=None),replace(option("r","right_landing"),handback_frame=None)]
    assert assess(opts,no_full).mode=="lower_bound"


def test_unknown_handback_cannot_be_satisfied_by_short_scan():
    opt=replace(option("d","dash_out"),handback_frame=None)
    assert assess([opt],lambda o:o.short_scan).verdict=="unchecked"
    resolved=lambda o:FullContinuationScan(scan(first=149,last=200,path=o.path_ref),200)
    assert assess([opt],resolved).mode=="full_exit"
    blocked=lambda o:FullContinuationScan(scan(first=149,last=180,path=o.path_ref),200)
    assert assess([opt],blocked).verdict=="unchecked"


def test_checkpoint_resumption_keeps_original_total_horizon(params,terrain):
    from ssbot.combat.knife_chain_nominal import NominalUnsupported
    _,p,raw,sim=preview(params,terrain)
    parent=compile_path(p.draft,raw,sim,0.,stage="commitment",first_mask=p.mask)
    bs=ChainSim(parent.states[:,-1],np.array([parent.queued_next],np.int64),parent.hold_end,params,terrain,parent.through,parent.through)
    short=compile_path(parent.runner_end,parent.raw_end,bs,parent.game[-1],stage="continuation",
        first_mask=0,branch="left_landing",known_press=parent.press_frame,stop_after=12)
    with pytest.raises(NominalUnsupported):finish_post(short,params,terrain,profile=NominalProfile(max_frames=24))
