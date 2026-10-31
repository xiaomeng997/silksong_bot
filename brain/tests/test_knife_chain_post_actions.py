"""Ordinary post types are fresh model rows, not a second chain/input owner."""
import numpy as np
import pytest
from ssbot.knowledge import kinematics as km
from ssbot.combat.knife_chain_nominal import compile_path,NominalProfile,NominalUnsupported
from ssbot.combat.knife_chain_post_actions import ordinary_post
from ssbot.combat.knife_chain_b2 import NativeChainB2
from tests.test_knife_chain_b2 import params,terrain,preview


def parent(params,terrain):
    _,p,s,sim=preview(params,terrain)
    return compile_path(p.draft,s,sim,0.,stage="commitment",first_mask=p.mask)


@pytest.mark.parametrize("kind",["left_landing","right_landing","dash_out"])
def test_fresh_ordinary_option_uses_original_physics_and_current_prefix(params,terrain,kind):
    p=parent(params,terrain);old=p.states.copy()
    short=ordinary_post(p,params,terrain,kind=kind)
    assert short.commands[0]==p.queued_next and len(short.commands)==12
    expected=km.rollout(p.states[:,-1],short.latched[None,:],params,terrain)
    np.testing.assert_allclose(short.box,expected.box[0],atol=1e-12,rtol=0)
    np.testing.assert_array_equal(short.flags,expected.flags[0])
    assert short.first_draft is None and short.runner_end is None and not short.assumptions["input_owner"]
    assert NativeChainB2.continuation_executable(kind,short)
    np.testing.assert_array_equal(old,p.states)
    full=ordinary_post(p,params,terrain,kind=kind,full=True)
    assert full.end=="handback" and full.flags[-1]&km.F_GROUND
    np.testing.assert_allclose(full.box[:13],short.box,atol=1e-12,rtol=0)
    assert full.contact_frame is None and len(full.commands)<=160


def test_dash_cooldown_is_not_counted_as_an_executable_type(params,terrain):
    p=parent(params,terrain);p.states[km.DASH_CD,-1]=1.
    row=ordinary_post(p,params,terrain,kind="dash_out")
    assert not NativeChainB2.continuation_executable("dash_out",row)


def test_full_post_must_reach_ground_within_original_budget(params,terrain):
    p=parent(params,terrain)
    with pytest.raises(NominalUnsupported):ordinary_post(p,params,terrain,kind="left_landing",profile=NominalProfile(max_frames=24),full=True)
