import pytest

from ssbot.tools import cstate

NAMES = [f"b{i}" for i in range(92)]  # 1.0.30000 has 92 public bools (m0 §3.1)


def test_roundtrip_across_the_word_boundary():
    values = {"b0": True, "b63": True, "b64": True, "b91": True}
    words = cstate.encode(values, NAMES)
    assert len(words) == 2
    assert words[0] == (1 << 0) | (1 << 63)
    assert words[1] == (1 << 0) | (1 << 27)
    decoded = cstate.decode(words, NAMES)
    assert [n for n, v in decoded.items() if v] == ["b0", "b63", "b64", "b91"]


def test_word_count_must_match_schema():
    with pytest.raises(ValueError):
        cstate.decode([0], NAMES)


def test_ints():
    names = ["attackCount", "downspikeInvulnerabilitySteps", "toolThrowCount", "throwingToolVertical"]
    assert cstate.ints([1, 8, 0, -1], names)["downspikeInvulnerabilitySteps"] == 8
    with pytest.raises(ValueError):
        cstate.ints([1], names)
