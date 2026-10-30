"""Prepared-key runtime candidates still query CURRENT complete geometry.

Modeled bounce fixtures exercise the propose/cache/geometry/admission integration;
they provide no evidence of an observed bounce or live closed-loop safety.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest

from ssbot.combat.knife_chain_b2 import NativeChainB2
from ssbot.combat.knife_chain_nominal import logical_copy
from tests.test_knife_chain_b2 import params,terrain,runner,geometry
from tests.test_knife_chain_post import setup


@pytest.mark.parametrize("hazard_kind",["delayed","move"])
def test_cache_hit_cannot_keep_a_previous_clear_own_rune_or_target_remainder_verdict(params,terrain,geometry,monkeypatch,hazard_kind):
    import ssbot.combat.knife_chain_b2 as mod
    parent,paths,sim,move=setup(params,terrain)
    raw=deepcopy(parent.raw_end);frame=sim.f;game=float(parent.game[-1])
    n=NativeChainB2(runner_factory=runner,probe_ref="post-geometry-test")
    n.begin(raw);n._clock=game;n._clock_known=True
    n.prepare(raw,ground=False,accepting=True,sim=sim)
    n.runner=logical_copy(parent.runner_end)
    n._post_seed=logical_copy(parent.runner_end)
    n.post_context={"move":move,"bounce":frame}
    preview=SimpleNamespace(draft=parent.runner_end,mask=0)
    monkeypatch.setattr(n,"_preview",lambda:(preview,move))
    for kind,path in paths.items():n._remember_post_keys(path,kind,move,frame)
    def no_full_regeneration(*args,**kw):
        pytest.fail("fixture should hit all three prepared-key candidates")
    monkeypatch.setattr(mod,"compile_path",no_full_regeneration)
    _,rs,_=geometry;rs.samples=(0,256)
    prefs=SimpleNamespace(weights={"hit":10.},stance_x=35.,boss_x=None,risk_x=np.array([]),risk=np.array([]))
    forecast=SimpleNamespace(rs=rs)
    # First all modeled candidate paths are clear. No safety verdict goes into
    # the template; it still contains only desired keys and causal identity.
    clear=n.propose(None,None,sim.start,sim.hold,sim.prefix,forecast,prefs,None)
    assert clear is not None and clear.stage=="continuation"
    used=n.counts["b2_post_keys_reused"]
    assert used==3
    calls=[]
    def late_own_contact(x,y,t,owners):
        answer=np.zeros(np.asarray(x).shape,bool)
        if 7 in owners:
            # The final handback is after the actual/model start's 8-step
            # protection. This remains target-owned even for the rune case.
            answer[:,-1]=True;calls.append(len(t))
        return answer
    rs.occupied_only=late_own_contact
    if hazard_kind=="delayed":rs.occupied_hazards=late_own_contact
    # Keep the SAME template and current start; only fresh hazard information
    # changed. Both the target's own delayed rune and its remaining move must
    # now reject every cache candidate, with no current-slam admission in post.
    rejected=n.propose(None,None,sim.start,sim.hold,sim.prefix,forecast,prefs,None)
    assert rejected is None and calls
    assert n.counts["b2_post_keys_reused"]==used+3
    assert n.counts["b2_post_keys_miss"]==0
    assert n._hit is None and n._accepted is None
