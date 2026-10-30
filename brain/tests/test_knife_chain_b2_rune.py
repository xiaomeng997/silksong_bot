"""Owner attribution at the h2 guard boundary; geometry keeps every hazard."""
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat.knife_chain_slam import g_claw_bomb


def test_own_small_rune_is_left_to_the_planner_not_two_clapper_unsupported():
    bombs=np.array([[7,10.,3.,2.,0.,20.]])
    x=SimpleNamespace(v={"iid":7},obs=SimpleNamespace(bombs=bombs))
    before=bombs.copy()
    assert not g_claw_bomb(x,None)
    np.testing.assert_array_equal(before,bombs)


@pytest.mark.parametrize("owner",[0,8])
def test_unknown_or_other_small_rune_stays_explicitly_unsupported(owner):
    bombs=np.array([[7,10.,3.,2.,0.,20.],[owner,12.,3.,2.,0.,20.]])
    x=SimpleNamespace(v={"iid":7},obs=SimpleNamespace(bombs=bombs))
    with pytest.raises(NotImplementedError,match="another Clapper"):
        g_claw_bomb(x,None)
