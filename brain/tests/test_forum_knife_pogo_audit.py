import numpy as np
import pytest
from ssbot.tools.forum_knife_pogo_audit import counter_after_steps


def test_zero_physics_does_not_spend_protection_and_two_steps_spend_two():
    assert counter_after_steps(8, [1,0,1,2,0,1,1,1,1]).tolist() == [7,7,6,4,4,3,2,1,0]


def test_protection_never_goes_negative_or_ignores_invalid_counts():
    assert counter_after_steps(1, [2,0,1]).tolist() == [0,0,0]
    with pytest.raises(ValueError): counter_after_steps(8, [1,.5])
    with pytest.raises(ValueError): counter_after_steps(8, [-1])
