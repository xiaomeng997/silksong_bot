"""Two-monster lowhop cannot own a standing band occupied by the other body."""
import pytest

from ssbot.combat import rune_lowhop as LH, two_play as TP, push_cast as PC
from tests.test_sp9 import two_state


@pytest.fixture(autouse=True)
def fixed_profile(monkeypatch):
    monkeypatch.setattr(LH, "BOMBS2", False)
    monkeypatch.setattr(PC, "PMCAST", False)
    monkeypatch.setenv("SSBOT_FORUM_TWO_GUARD_SET", "low=0,body_pad=0.55")


def scene(face=1, other="Idle", occupied=True):
    s = two_state(1000, "Spell Antic", 0., x_rel=10., flip=face > 0,
                  b_st=other, b_x=31. + face * (4.1 if occupied else 20.))
    return s


@pytest.mark.parametrize("face", [-1, 1])
@pytest.mark.parametrize("guard_on", [False, True])
@pytest.mark.parametrize("other", ["Idle", "Walk"])
def test_occupied_stance_never_starts_even_without_optional_low_guard(monkeypatch, face, guard_on, other):
    monkeypatch.setattr(TP, "GUARD", guard_on)
    h = LH.RuneLowHop(two=True)
    assert h.step(1000, scene(face, other), False, t_game=1000/60.) is None
    assert h.run is None and h.why_not.get("other body") == 1


@pytest.mark.parametrize("face", [-1, 1])
def test_body_entering_stance_aborts_uncommitted_run(face):
    h = LH.RuneLowHop(two=True)
    assert h.step(1000, scene(face, occupied=False), True, t_game=1000/60.) is not None
    assert h.run is not None and not h.critical()
    s = scene(face); s["f"] = 1001
    assert h.step(1001, s, True, t_game=1001/60.) is None
    assert h.run is None and h.done[-1].why == "other body"


def test_occupied_stance_does_not_cut_an_already_committed_jump_hold(monkeypatch):
    h = LH.RuneLowHop(two=True)
    h.run = LH.Hop(iid=7, face=1, f0=1000, ta=1000/60., fa=1000,
                   d0=10., ground0=True, hp0=9, phase="hop", P=0, H=12, k=2)
    assert h.critical()
    monkeypatch.setattr(h, "_step", lambda *args: LH.M_J)
    assert h.step(1000, scene(), False, t_game=1000/60.) == LH.M_J
    assert h.run is not None


def test_clear_stance_and_single_monster_keep_existing_masks():
    s = scene(occupied=False)
    h = LH.RuneLowHop(two=True)
    assert h.step(1000, s, True, t_game=1000/60.) == LH.M_L
    s["ents"] = s["ents"][:1]
    h = LH.RuneLowHop()
    assert h.step(1000, s, True, t_game=1000/60.) == LH.M_L


def test_stance_gate_does_not_reintroduce_full_way_body_guard():
    s = scene(occupied=False)
    # Body lies on the way, but outside the standing band. This admission
    # preserves fp1 scope; it is not a safety certificate for that path.
    s["ents"][1]["colliders"] = [{"name": LH.CLAPPER, "enabled": True,
        "verts_world": [37.8, 3., 39.8, 3., 39.8, 7., 37.8, 7.]}]
    h = LH.RuneLowHop(two=True)
    assert h.step(1000, s, True, t_game=1000/60.) == LH.M_L


def test_guard_body_pad_configuration_applies_even_when_low_is_off(monkeypatch):
    monkeypatch.setattr(TP, "GUARD", True)
    monkeypatch.setenv("SSBOT_FORUM_TWO_GUARD_SET", "low=0,body_pad=1.0")
    s = scene(occupied=False)
    s["ents"][1]["colliders"] = [{"name": LH.CLAPPER, "enabled": True,
        "verts_world": [36.3, 3., 37.3, 3., 37.3, 7., 36.3, 7.]}]
    h = LH.RuneLowHop(two=True)
    assert h.step(1000, s, True, t_game=1000/60.) is None
    assert h.why_not.get("other body") == 1
