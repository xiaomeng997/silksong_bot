"""Task 182 seq 304: the big rune circle's life in the low hop's start gate. The pooled object leaves the entity list some
time after its burst and comes back unlit for the next cast: that circle is a new one, at a new place or the same."""
import pytest

from ssbot.combat import cast_stab as CS, push_cast as PC, rune_life as RL, rune_lowhop as LH
from tests.test_sp9 import two_state

R = 7.186814308166504
RIID = -500


@pytest.fixture(autouse=True, params=[False, True], ids=["b2off", "b2on"])
def profile(monkeypatch, request):
    monkeypatch.setattr(LH, "BOMBS2", request.param)
    monkeypatch.setattr(PC, "PMCAST", False)
    monkeypatch.setenv("SSBOT_FORUM_TWO_GUARD_SET", "low=0,body_pad=0.55")


def rune(cx, lit=False, iid=RIID):
    return {"iid": iid, "type_key": "damager", "category": "hazard", "pos": [cx, 3.342, 0.], "hidden": False,
            "colliders": [{"kind": "circle", "name": "damager", "enabled": lit, "r": R,
                           "verts_world": [cx - R, 3.342, cx, 3.342 + R, cx + R, 3.342, cx, 3.342 - R]}]}


def st(f, *runes):
    """A STATE listing a Clapper and these circle objects (none: the objects have left the list)."""
    return {"f": f, "ents": [{"iid": 7, "type_key": LH.CLAPPER, "pos": [31., 7.45]}, *runes]}


def centres(spans):
    return sorted(round(0.5 * (a + b), 3) for a, b in spans)


def low(two=True):
    return LH.RuneLowHop(two=two)


def burn(h, cx, f0=100, iid=RIID, gone=True):
    """One whole life of the object at cx: appears at f0, lit at + 65 .. + 72, stays unlit to + 180, then (gone) leaves."""
    h.observe(f0, st(f0, rune(cx, iid=iid)))
    h.observe(f0 + 65, st(f0 + 65, rune(cx, True, iid=iid)))
    h.observe(f0 + 73, st(f0 + 73, rune(cx, iid=iid)))
    h.observe(f0 + 180, st(f0 + 180, rune(cx, iid=iid)))
    if gone:
        h.observe(f0 + 181, st(f0 + 181))
    return f0 + 181


# ---- the memory ----

def test_first_life_is_pending_then_lit_then_spent():
    h = low()
    assert centres(h._rune_threats(100, st(100, rune(30.)))) == [30.]
    assert centres(h._rune_threats(164, st(164, rune(30.)))) == [30.]
    assert centres(h._rune_threats(165, st(165, rune(30., True)))) == [30.]
    assert h._rune_threats(173, st(173, rune(30.))) == []


def test_the_burst_one_stays_spent_for_its_whole_stay():
    h = low()
    h.observe(100, st(100, rune(30.)))
    h.observe(165, st(165, rune(30., True)))
    assert all(h._rune_threats(f, st(f, rune(30.))) == [] for f in range(173, 300))


@pytest.mark.parametrize("dx", [0., 0.3, -6., 9.], ids=["same_place", "near", "left", "right"])
def test_the_next_circle_of_the_object_is_pending_again(dx):
    h = low()
    f = burn(h, 30.)
    assert centres(h._rune_threats(f + 40, st(f + 40, rune(30. + dx)))) == [round(30. + dx, 3)]


def test_the_new_life_has_its_own_clock():
    h = low()
    f = burn(h, 30.) + 40
    h.observe(f, st(f, rune(30.)))
    assert centres(h._rune_threats(f + RL.PENDING_F - 1, st(f + RL.PENDING_F - 1, rune(30.)))) == [30.]
    assert h._rune_threats(f + RL.PENDING_F, st(f + RL.PENDING_F, rune(30.))) == []


def test_the_new_life_burns_and_is_spent_again():
    h = low()
    f = burn(h, 30.) + 40
    h.observe(f, st(f, rune(38.)))
    assert centres(h._rune_threats(f + 65, st(f + 65, rune(38., True)))) == [38.]
    assert h._rune_threats(f + 73, st(f + 73, rune(38.))) == []


def test_placed_anew_without_being_seen_gone_is_a_new_circle():
    h = low()
    f = burn(h, 30., gone=False)
    assert centres(h._rune_threats(f, st(f, rune(30.51)))) == [30.51]


def test_a_small_shift_in_place_is_the_same_circle():
    h = low()
    f = burn(h, 30., gone=False)
    assert h._rune_threats(f, st(f, rune(30.49))) == []


def test_two_circles_live_apart():
    h = low()
    burn(h, 30., gone=False)                                            # 30: spent, still there (to 280)
    h.observe(281, st(281, rune(30.), rune(44., iid=-501)))
    assert centres(h._rune_threats(282, st(282, rune(30.), rune(44., iid=-501)))) == [44.]
    h.observe(283, st(283, rune(44., iid=-501)))                        # 30 left; 44 stays
    assert centres(h._rune_threats(330, st(330, rune(30.), rune(44., iid=-501)))) == [30., 44.]
    assert centres(h._rune_threats(347, st(347, rune(30.), rune(44., True, iid=-501)))) == [30., 44.]
    assert centres(h._rune_threats(356, st(356, rune(30.), rune(44., iid=-501)))) == [30.]


@pytest.mark.parametrize("empty", [{"f": 0, "ents": []}, {"f": 0}], ids=["empty_list", "no_key"])
def test_a_state_without_entities_is_no_absence(empty):
    h = low()
    f = burn(h, 30., gone=False)
    assert h._rune_threats(f, dict(empty, f=f)) == []
    assert h._rune_threats(f + 1, st(f + 1, rune(30.))) == []


def test_lit_in_place_after_its_burst_is_a_threat_while_lit():
    h = low()
    f = burn(h, 30., gone=False)
    assert centres(h._rune_threats(f, st(f, rune(30., True)))) == [30.]
    assert h._rune_threats(f + 1, st(f + 1, rune(30.))) == []


def test_never_lit_and_timed_out_stays_out_until_it_leaves():
    h = low()
    h.observe(100, st(100, rune(30.)))
    assert h._rune_threats(100 + RL.PENDING_F, st(100 + RL.PENDING_F, rune(30.))) == []
    f = 101 + RL.PENDING_F
    h.observe(f, st(f))
    h.observe(f + 5, st(f + 5))
    assert h._rune_threats(f + 5, st(f + 5, rune(30.))) == []                # (no new look at the same frame)
    assert centres(h._rune_threats(f + 6, st(f + 6, rune(30.)))) == [30.]    # listed again after ABSENT_F frames: a new circle


def test_two_looks_in_one_frame_agree():
    h = low()
    f = burn(h, 30.) + 40
    a = h._rune_threats(f, st(f, rune(30.)))
    assert h._rune_threats(f, st(f, rune(30.))) == a and centres(a) == [30.]


# ---- the start gate (production step) ----

def scene(f, face=1, runes=(), x_rel=10., cx=31., hx=None, ground=True, tin=0.):
    s = two_state(f, "Spell Antic", tin, x_rel=x_rel, cx=cx, flip=face > 0, ground=ground, b_st="Idle",
                  b_x=cx + face * 26., hx=hx)
    s["ents"].extend(runes)
    return s


def toward(face):
    return LH.M_L if face > 0 else LH.M_R


@pytest.mark.parametrize("face", [1, -1])
@pytest.mark.parametrize("dx", [0., 6.], ids=["same_place", "new_place"])
def test_a_reused_pending_circle_over_the_stance_refuses_the_start(face, dx):
    h = low()
    x = 31. + face * 4.1
    f = burn(h, x + dx) + 40
    new = rune(x)
    h.observe(f, st(f, new))
    s = scene(f + 18, face, [new])
    h.observe(f + 18, s)
    assert h.step(f + 18, s, True, t_game=(f + 18) / 60.) is None
    assert h.run is None and h.why_not == {"rune": 1}


@pytest.mark.parametrize("face", [1, -1])
def test_she_inside_a_reused_circle_is_refused_with_the_stance_clear(face):
    h = low()
    x = 31. + face * 15.                                                # covers her at + 10, not the stance at + 3.6 .. 4.6
    f = burn(h, x) + 40
    new = rune(x)
    h.observe(f, st(f, new))
    s = scene(f + 18, face, [new])
    assert h.step(f + 18, s, True, t_game=(f + 18) / 60.) is None
    assert h.why_not == {"rune": 1}


@pytest.mark.parametrize("face", [1, -1])
def test_the_burst_circle_of_this_life_keeps_the_start(face):
    h = low()
    x = 31. + face * 4.1
    f = burn(h, x, gone=False)
    s = scene(f, face, [rune(x)])
    assert h.step(f, s, True, t_game=f / 60.) == toward(face)
    assert h.run is not None and "rune" not in h.why_not


@pytest.mark.parametrize("face", [1, -1])
def test_no_circle_keeps_the_start(face):
    h = low()
    assert h.step(1000, scene(1000, face), True, t_game=1000 / 60.) == toward(face)
    assert h.run is not None and "rune" not in h.why_not


@pytest.mark.parametrize("face", [1, -1])
def test_a_reused_circle_away_from_her_way_keeps_the_start(face):
    h = low()
    x = 31. - face * 12.                                                # behind the caster
    f = burn(h, x) + 40
    new = rune(x)
    h.observe(f, st(f, new))
    assert h.step(f + 18, scene(f + 18, face, [new]), True, t_game=(f + 18) / 60.) == toward(face)
    assert h.run is not None


def test_a_refused_cast_is_looked_at_once():
    h = low()
    x = 35.1
    f = burn(h, x) + 40
    new = rune(x)
    h.observe(f, st(f, new))
    assert h.step(f + 18, scene(f + 18, 1, [new]), True, t_game=(f + 18) / 60.) is None
    assert h.step(f + 19, scene(f + 19, 1, [new], tin=1 / 60.), True, t_game=(f + 19) / 60.) is None
    assert h.run is None and h.why_not == {"rune": 1} and h.n_cast == 1


def test_the_next_cast_starts_once_that_circle_has_burst():
    h = low()
    x = 35.1
    f = burn(h, x) + 40
    new = rune(x)
    h.observe(f, st(f, new))
    assert h.step(f + 18, scene(f + 18, 1, [new]), True, t_game=(f + 18) / 60.) is None
    h.observe(f + 65, st(f + 65, rune(x, True)))
    g = f + 200
    assert h.step(g, scene(g, 1, [rune(x)]), True, t_game=g / 60.) == LH.M_L
    assert h.run is not None and h.why_not == {"rune": 1} and h.n_cast == 2


def test_a_new_circle_does_not_cut_a_committed_hop(monkeypatch):
    h = low()
    x = 35.1
    f = burn(h, x) + 40
    new = rune(x)
    h.observe(f, st(f, new))
    h.run = LH.Hop(iid=7, face=1, f0=f, ta=f / 60., fa=f, d0=10., ground0=True, hp0=9, phase="hop", P=0, H=12, k=2)
    assert h.critical()
    monkeypatch.setattr(h, "_step", lambda *args: LH.M_J)
    assert h.step(f, scene(f, 1, [new]), False, t_game=f / 60.) == LH.M_J
    assert h.run is not None


def test_a_new_circle_over_her_stance_ends_a_running_stance():
    # (Task 182 seq 310 turned this round: the run's own check every tick, its critical window excepted: test_a_new_circle_does_not_cut_a_committed_hop)
    h = low()
    assert h.step(1000, scene(1000, 1), True, t_game=1000 / 60.) == LH.M_L
    x = 35.1
    f = 1001
    s = scene(f, 1, [rune(x)], tin=1 / 60.)
    h.observe(f, s)
    assert h.step(f, s, True, t_game=f / 60.) is None and h.run is None and h.done[-1].why == "rune"


# ---- the five recorded starts of the 50 bouts of 7418c1c5 (numbers from the recordings; the positions of the earlier lives) ----

WITNESS = {
    "bout3": (12788, 29.085, 1, 30.933, False, (31.479, 33.859)),
    "bout8": (26190, 33.68, 1, 37.566, False, (35.344, 37.044)),
    "bout36": (103390, 27.652, 1, 32.307, False, (33.566, 29.322, 35.681)),
    "bout41": (118618, 28.947, -1, 18.917, True, (31.562, 27.268)),
    "bout45": (130049, 36.207, -1, 34.304, False, (24.612, 33.886)),
}


@pytest.mark.parametrize("name", list(WITNESS))
def test_the_recorded_start_is_refused(name):
    F, cx, face, hx, ground, lives = WITNESS[name]
    h = low()
    f = F - 18 - 400 * (len(lives) - 1)
    for c in lives[:-1]:
        f = burn(h, c, f0=f) + 219
    new = rune(lives[-1])
    h.observe(F - 18, st(F - 18, new))
    s = scene(F, face, [new], cx=cx, hx=hx, ground=ground)
    assert h.step(F, s, ground, t_game=F / 60.) is None
    assert h.run is None and h.why_not == {"rune": 1}


@pytest.mark.parametrize("name", list(WITNESS))
def test_the_recorded_start_with_only_a_burst_circle_starts(name):
    F, cx, face, hx, ground, lives = WITNESS[name]
    h = low()
    f = burn(h, lives[-1], f0=F - 180, gone=False)
    assert f == F + 1
    s = scene(F + 1, face, [rune(lives[-1])], cx=cx, hx=hx, ground=ground)
    h.step(F + 1, s, ground, t_game=(F + 1) / 60.)
    assert "rune" not in h.why_not and h.n_cast == 1
