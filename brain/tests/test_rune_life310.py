"""Task 182 seq 310: the big rune circles' lives (combat.rune_life.RuneCircles, one record per generation of an object, shared by every script), and the
last check on a final key (exit_veto over the tick's hero model). The four orders big / small are covered by the shared rows the check reads."""
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import air_chain as ac
from ssbot.combat import cast_stab as CS
from ssbot.combat import claw_strike as cs_
from ssbot.combat import evade_chase as EC
from ssbot.combat import rune_life as RL
from ssbot.combat import rune_lowhop as LH
from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from ssbot.knowledge import kinematics as kin
from tests.test_slam_play import state
from tests.test_sp9 import two_state

REPO = Path(__file__).resolve().parents[2]
PARAMS = kin.HeroParams.load(REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_wanderer_forum.json")
TERR = kin.Terrain2D.from_boxes([(-200.0, cs_.FLOOR - 10.0, 260.0, cs_.FLOOR), (0.0, 0.0, 14.01, 40.0), (48.99, 0.0, 70.0, 40.0)])
FT = 1.0 / 60.0
R = 7.186814308166504
FLOOR = cs_.FLOOR


def rune(cx, lit=False, iid=-500):
    return {"iid": iid, "type_key": "damager", "category": "hazard", "pos": [cx, 3.342, 0.], "hidden": False,
            "colliders": [{"kind": "circle", "name": "damager", "enabled": lit, "r": R,
                           "verts_world": [cx - R, 3.342, cx, 3.342 + R, cx + R, 3.342, cx, 3.342 - R]}]}


def st(f, *runes):
    return {"f": f, "ents": [{"iid": 7, "type_key": "Song Heavy Sentry", "pos": [31., 7.45]}, *runes]}


def life(c, cx, f0=100, iid=-500):
    """One whole life: appears at f0, lit at + 65 .. + 72 (game frames), unlit to + 180."""
    c.update(f0, st(f0, rune(cx, iid=iid)))
    c.update(f0 + 65, st(f0 + 65, rune(cx, True, iid=iid)))
    c.update(f0 + 72, st(f0 + 72, rune(cx, True, iid=iid)))
    c.update(f0 + 73, st(f0 + 73, rune(cx, iid=iid)))
    c.update(f0 + 180, st(f0 + 180, rune(cx, iid=iid)))
    return f0 + 180


def centres(c):
    return sorted(round(0.5 * (a + b), 2) for a, b in c.spans())


# ---- the ledger: one record per generation ----

def test_pending_then_lit_then_spent_for_the_rest_of_its_stay():
    c = RL.RuneCircles()
    c.update(100, st(100, rune(30.)))
    assert centres(c) == [30.]
    c.update(165, st(165, rune(30., True)))
    assert centres(c) == [30.]
    c.update(173, st(173, rune(30.)))
    assert c.spans() == []
    for f in range(174, 300, 7):
        c.update(f, st(f, rune(30.)))
        assert c.spans() == []                    # the residue is no new circle


@pytest.mark.parametrize("dx", [0., 0.3, -6., 9.], ids=["same_place", "near", "left", "right"])
def test_the_object_back_after_it_left_is_a_new_circle(dx):
    c = RL.RuneCircles()
    f = life(c, 30.)
    c.update(f + 1, st(f + 1))                    # left the list: the first frame without it
    c.update(f + 6, st(f + 6))                    # still gone at + 5: its record ends
    c.update(f + 40, st(f + 40, rune(30. + dx)))
    assert centres(c) == [round(30. + dx, 2)]


def test_a_new_generation_has_its_own_clock():
    c = RL.RuneCircles()
    f = life(c, 30.)
    c.update(f + 1, st(f + 1))
    c.update(f + 8, st(f + 8))
    c.update(f + 40, st(f + 40, rune(30.)))
    assert centres(c) == [30.]
    c.update(f + 40 + RL.PENDING_F - 1, st(f + 40 + RL.PENDING_F - 1, rune(30.)))
    assert centres(c) == [30.]
    c.update(f + 40 + RL.PENDING_F, st(f + 40 + RL.PENDING_F, rune(30.)))
    assert c.spans() == []                        # its schedule is over: not forever


def test_a_missing_frame_is_no_disappearance():
    c = RL.RuneCircles()
    c.update(100, st(100, rune(30.)))
    # a STATE without entities, or with the entity list without it for fewer than ABSENT_F frames: nothing changes
    c.update(101, {"f": 101, "ents": []})
    c.update(102, {"f": 102})
    assert centres(c) == [30.]
    c.update(103, st(103))
    c.update(107, st(107))
    assert centres(c) == [30.]
    c.update(108, st(108, rune(30.)))
    assert centres(c) == [30.] and c.recs[-500].first_f == 100     # the same circle, same clock


def test_no_data_for_many_frames_is_still_no_disappearance():
    c = RL.RuneCircles()
    c.update(100, st(100, rune(30.)))
    c.update(120, st(120, rune(30.)))             # nothing in between: frames not received say nothing
    assert centres(c) == [30.] and c.recs[-500].first_f == 100


def test_moved_is_a_new_circle_a_small_shift_is_not():
    c = RL.RuneCircles()
    f = life(c, 30.)
    c.update(f + 1, st(f + 1, rune(30.49)))
    assert c.spans() == []                        # the residue moved 0.49: the same spent object
    c = RL.RuneCircles()
    f = life(c, 30.)
    c.update(f + 1, st(f + 1, rune(30.51)))
    assert centres(c) == [30.51]                  # placed anew


def test_lit_again_in_place_after_its_burst_is_a_new_life():
    c = RL.RuneCircles()
    f = life(c, 30.)
    c.update(f + 1, st(f + 1, rune(30., True)))
    assert centres(c) == [30.] and c.recs[-500].first_f == f + 1
    c.update(f + 2, st(f + 2, rune(30.)))
    assert c.spans() == []


def test_one_burst_never_ends_another_circle():
    """big -> big: two generations alive at once, neighbours or not, each on its own clock (no matching by place)."""
    c = RL.RuneCircles()
    a, b = -500, -501
    c.update(100, st(100, rune(30., iid=a)))
    c.update(141, st(141, rune(30., iid=a), rune(30.2, iid=b)))        # born 41 frames apart, almost the same centre
    assert centres(c) == [30., 30.2]
    c.update(165, st(165, rune(30., True, iid=a), rune(30.2, iid=b)))  # A lights, B to come
    c.update(173, st(173, rune(30., iid=a), rune(30.2, iid=b)))        # A burnt out
    assert centres(c) == [30.2]
    c.update(206, st(206, rune(30., iid=a), rune(30.2, True, iid=b)))  # B lights
    assert centres(c) == [30.2]
    c.update(214, st(214, rune(30., iid=a), rune(30.2, iid=b)))
    assert c.spans() == []


def test_an_owner_is_not_a_condition():
    """A circle does not belong to who is asking: the record has no owner to skip."""
    c = RL.RuneCircles()
    c.update(100, st(100, rune(30.)))
    assert centres(c) == [30.]                    # no Clapper state, no owner: it counts


def test_one_frame_reads_once():
    c = RL.RuneCircles()
    c.update(100, st(100, rune(30.)))
    c.update(100, st(100, rune(35.)))             # a second look at the same frame changes nothing
    assert centres(c) == [30.]


def test_rows_pending_window_from_its_own_clock():
    c = RL.RuneCircles()
    c.update(100, st(100, rune(30.)), t_game=100 * FT)
    r = c.rows()
    assert r.shape == (1, 6)
    assert r[0, 1] == 30. and r[0, 3] == RL.RUNE_R and r[0, 4] == 65 and r[0, 5] == 74
    c.update(130, st(130, rune(30.)), t_game=130 * FT)
    r = c.rows()
    assert r[0, 4] == 35 and r[0, 5] == 44
    # the game clock stands still in a hit-stop: the frames do not count
    c.update(160, st(160, rune(30.)), t_game=130 * FT)
    r = c.rows()
    assert r[0, 4] == 35 and r[0, 5] == 44
    # lit now: 0 .. its end
    c.update(165, st(165, rune(30., True)), t_game=165 * FT)
    r = c.rows()
    assert r[0, 4] == 0 and r[0, 5] == 7
    c.update(173, st(173, rune(30.)), t_game=173 * FT)
    assert c.rows().shape == (0, 6)


# ---- the hazard path check ----

def big(cx, on, off, cy=3.34):
    return np.array([[-500., cx, cy, RL.RUNE_R, on, off]])


def bomb(cx, on, off, cy=3.67):
    return np.array([[7., cx, cy, 2.166, on, off]])


def test_path_exposed_reads_the_rune_own_frames():
    xs = np.full(80, 30.)
    assert RL.path_exposed(xs, np.zeros(80), big(30., 10., 20.)) == "circle"
    # on the rune's frames she is elsewhere
    xs = np.r_[np.full(30, 45.), np.full(50, 30.)]
    assert RL.path_exposed(xs, np.zeros(80), big(30., 10., 20.)) is None
    # far above the octagon's corner (0.3 u inside the x edge, 6 u up)
    assert RL.path_exposed(np.full(40, 30. + 7.0), np.full(40, 6.), big(30., 0., 39.)) is None
    # a bomb window
    assert RL.path_exposed(np.full(40, 20.), np.zeros(40), bomb(20., 5., 8.)) == "bomb"
    assert RL.path_exposed(np.full(40, 20.), np.full(40, 6.), bomb(20., 5., 8.)) is None   # over its top


def test_path_exposed_no_rows():
    assert RL.path_exposed(np.zeros(5), np.zeros(5), None) is None
    assert RL.path_exposed(np.zeros(5), np.zeros(5), np.zeros((0, 6))) is None


# ---- the last check on a key: the real hero model ----

def sim_for(hx, f=1000, ground=True, vy=0.0, vx=0.0, prefix=(0,)):
    S = kin.initial_state(PARAMS, hx, FLOOR + cs_.POS_DY, vy=vy, facing=1, ground=ground)
    S = np.asarray(S, float).copy()
    S[kin.VX] = vx
    return ac.ChainSim(S, np.array(prefix, np.int64), kin.HoldState.idle(1), PARAMS, TERR, f - len(prefix) + 1, f)


L, R_, DASH = kin.B_LEFT, kin.B_RIGHT, kin.B_DASH


def test_walking_into_a_circle_about_to_light_is_refused():
    """0.9 u inside its edge, lit in 10 frames: one more step left and she cannot be out in time, with the margin; right now she can still run out."""
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), L, big(30., 10., 18.))
    assert veto and info["now"] and not info["after"]


def edge():
    return 30. + RL.RUNE_R + 0.25


def test_now_is_read_without_the_margin():
    """Lit in 10 frames, dash on cooldown: right now she can still just run out (no margin asked of the way out she has now); after one step left she cannot."""
    S = kin.initial_state(PARAMS, edge() - 0.9, FLOOR + cs_.POS_DY, vy=0.0, facing=1, ground=True)
    S = np.asarray(S, float).copy()
    S[kin.DASH_CD] = 0.6
    sim = ac.ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERR, 1000, 1000)
    veto, info = RL.exit_veto(sim, L, big(30., 10., 18.))
    assert veto and info["now"] and not info["after"]


def test_the_key_away_is_never_refused():
    veto, _ = RL.exit_veto(sim_for(edge() - 0.9), R_, big(30., 10., 18.))
    assert not veto


def test_enough_time_to_walk_in_and_out_again_is_not_refused():
    veto, _ = RL.exit_veto(sim_for(edge() + 0.3), L, big(30., 60., 68.))
    assert not veto


def test_no_way_out_now_is_not_refused():
    """Deep inside and it lights soon: no key can help: the owner goes on as before."""
    veto, info = RL.exit_veto(sim_for(30.), L, big(30., 3., 11.))
    assert not veto and not info["now"]


def test_a_circle_that_has_burnt_out_blocks_nothing():
    veto, info = RL.exit_veto(sim_for(30.), L, big(30., -20., -10.))
    assert not veto and info is None


def test_a_side_slash_is_an_ordinary_key():
    """Sol's review of #372: the side slash has no owner-level path check: it is judged like a walk key, for every owner."""
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), L | kin.B_ATTACK, big(30., 10., 18.))
    assert veto and info is not None
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), L | kin.B_ATTACK, big(30., 10., 18.), strike_exempt=True)
    assert veto and info is not None          # (exempt owners are exempt for a down slash or a hook only)


def test_a_down_slash_press_is_not_looked_at_for_the_exempt_owners():
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), kin.B_DOWN | kin.B_ATTACK, big(30., 10., 18.), strike_exempt=True)
    assert not veto and info is None
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), kin.B_DOWN | kin.B_ATTACK, big(30., 10., 18.))
    assert info is not None                   # any other owner: the question is asked


def test_the_clawline_key_is_not_looked_at_for_the_exempt_owners():
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), L | RL.CLAW_BIT, big(30., 10., 18.), strike_exempt=True)
    assert not veto and info is None


def full_verdict(monkeypatch, sim, mask, rows):
    """The hero model alone, without the distance stage (its reference)."""
    with monkeypatch.context() as m:
        m.setattr(RL, "NEAR_F", 10 ** 6)
        return RL.exit_veto(sim, mask, rows)[0]


@pytest.mark.parametrize("prefix", [(0,), (kin.B_LEFT,), (kin.B_RIGHT,), (kin.B_LEFT, kin.B_LEFT), (kin.B_LEFT,) * 6, (kin.B_LEFT | kin.B_DASH,), (kin.B_RIGHT | kin.B_DASH,)],
                         ids=["none", "L", "R", "L2", "L6", "LD", "RD"])
def test_the_distance_check_never_passes_what_the_hero_model_refuses(monkeypatch, prefix):
    """Sol's PREFIX_CHECK372 cases and the grid around them: whatever the distance waves through, the hero model agrees with."""
    bad = []
    for inside in (-3.0, -2.0, -1.0, -0.5, -0.3, 0.3, 0.9, 1.5):
        for on in (4, 6, 10, 14, 20):
            for mask in (0, L, R_, kin.B_JUMP, L | kin.B_ATTACK, L | DASH):
                for vx in (0.0, -8.25, 8.25):
                    sim = sim_for(edge() - inside, prefix=prefix, vx=vx)
                    rows = big(30., on, on + 8)
                    fast = RL.exit_veto(sim, mask, rows)
                    if not fast[0] and full_verdict(monkeypatch, sim, mask, rows):
                        bad.append((inside, on, mask, vx, fast))
    assert not bad, bad


def hold_with(key_bit, age=50, latched=True, pending=0):
    h = kin.HoldState.idle(1)
    h.latched[0, key_bit] = latched
    h.desired[0, key_bit] = latched or pending > 0
    h.pending[0, key_bit] = pending
    h.age[0, key_bit] = age
    return h


def test_a_queued_dash_counts_for_the_distance_check():
    """Too far to walk onto the circle in time but the filter has a dash queued: the distance check cannot wave it through."""
    S = kin.initial_state(PARAMS, edge() + 2.5, FLOOR + cs_.POS_DY, vy=0.0, facing=1, ground=True)
    idle = ac.ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERR, 1000, 1000)
    assert RL.exit_veto(idle, 0, big(30., 8., 16.)) == (False, None)
    queued = ac.ChainSim(S, np.zeros(1, np.int64), hold_with(2, latched=False, pending=1), PARAMS, TERR, 1000, 1000)
    assert RL.exit_veto(queued, 0, big(30., 8., 16.))[1] is not None


def test_the_delayed_state_case_six_left_keys_in_flight():
    """Sol's PREFIX_CHECK372: fo 5 frames behind f (never in the 58 616 live decisions: all fo = f), x 37.437, six LEFT keys in flight, lit in 4 frames, RIGHT now: the hero model answers: refused."""
    veto, info = RL.exit_veto(sim_for(37.437, prefix=(L,) * 6), R_, big(30., 4., 12.))
    assert veto and info["after"] is False and info["now"] is True


@pytest.mark.parametrize("mask", [0, L, kin.B_JUMP], ids=["none", "left", "jump"])
def test_the_recorded_review_case_one_left_key_in_flight(mask):
    """Sol's PREFIX_CHECK372: x 37.737 (0.3 u outside its edge), LEFT in flight (fo = f), lit in 6 frames: the hero model answers it with the key in flight: no way out with the margin."""
    sim = sim_for(edge() + 0.3, prefix=(L,))
    assert sim.fo == sim.f
    veto, info = RL.exit_veto(sim, mask, big(30., 6., 14.))
    assert veto and info["after"] is False and info["now"] is True


def test_far_from_every_rune_nothing_is_rolled():
    """No hero model at all when the key cannot bring her onto a rune."""
    class NoRoll:
        off = 2
        start = kin.initial_state(PARAMS, 44.0, FLOOR + cs_.POS_DY, vy=0.0, facing=1, ground=True)
        prefix = np.zeros(1, np.int64)
        hold = kin.HoldState.idle(1)
        fo = f = 1000
        def roll(self, *a):
            raise AssertionError("rolled")
    assert RL.exit_veto(NoRoll(), L, big(20., 30., 38.)) == (False, None)
    assert RL.exit_veto(NoRoll(), L | DASH, big(20., 30., 38.)) == (False, None)


def test_small_then_small_two_casters_each_count():
    """small -> small: bombs of two owners: the first one's end does not lift the second one's, and the row owner is not a condition."""
    rows = np.r_[bomb(31.0, 8., 14.), np.array([[8., 29.0, 3.67, 2.166, 18., 26.]])]
    veto_a, info = RL.exit_veto(sim_for(30.0), L, rows)
    assert info is not None and info["n_bomb"] == 2
    # the first bomb burnt out, the second still to light: the rows of frames after the first show only the second
    rows_b = rows[rows[:, 5] >= 14.5]
    assert rows_b.shape == (1, 6) and rows_b[0, 1] == 29.0
    veto, info = RL.exit_veto(sim_for(30.0), L, rows_b)
    assert info is None or info["n_bomb"] == 1


def test_big_then_big_two_windows_are_kept_apart():
    """big -> big: the second circle's window is not ended by the first one's."""
    rows = np.r_[big(30., 20., 28.), big(32., 60., 68.)]
    assert RL.path_exposed(np.full(70, 31.), np.zeros(70), rows) == "circle"
    # after the first one's end, she stands on it, the second one still to light: path check sees the second
    after = rows[rows[:, 5] > 40.]
    assert after.shape == (1, 6) and after[0, 1] == 32.
    assert RL.path_exposed(np.full(70, 31.), np.zeros(70), after) == "circle"
    assert RL.path_exposed(np.full(70, 45.), np.zeros(70), after) is None


def test_a_bomb_on_her_x_counts_like_a_circle():
    """small: a bomb lights over her and over the way out she could still take a step to"""
    veto, info = RL.exit_veto(sim_for(30.), 0, bomb(30., 2., 9.))
    assert info["now"] or not veto


def test_big_then_small_either_keeps_the_circle():
    """big -> small: a bomb somewhere else does not lift the circle."""
    rows = np.r_[big(30., 10., 18.), bomb(38.7, 40., 48.)]
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), L, rows)
    assert veto and info["n_big"] == 1 and info["n_bomb"] == 1


def test_small_then_big_keeps_the_bomb():
    """small -> big: the bomb over the only way out counts when she walks toward it."""
    rows = np.r_[bomb(30.5, 8., 16.), big(14., 12., 20.)]
    veto, info = RL.exit_veto(sim_for(30.), L, rows)
    assert info is not None and info["n_bomb"] == 1 and info["n_big"] == 1


# ---- the scripts read the same record (a generation, not an iid) ----

def reused_ledger(cx=30., iid=-500):
    c = RL.RuneCircles()
    f = life(c, cx - 3., iid=iid)                  # an earlier life somewhere else
    c.update(f + 1, st(f + 1))
    c.update(f + 8, st(f + 8))
    return c, f + 40


def test_chase_sees_the_new_generation_of_a_reused_object():
    """Bout 11 / 15 (A1): the object's old life does not hide the new circle from the chase's way."""
    ec = EC.EvadeChase(one=True, two=True)
    c, f = reused_ledger()
    ec._life = c
    s = {"f": f, "hero": {"pos": [40.0, 4.56], "box": [39.75, 3.015, 40.25, 5.09], "vel": [0., 0.]},
         "ents": [{"iid": 7, "type_key": "Song Heavy Sentry", "pos": [24.0, 7.45], "flipX": True, "fsms": [{"name": "Control", "state": EC.EVADE, "t": 0.1}]},
                  rune(30.)]}
    c.update(f, s)
    assert ec._rune_in_way(f, s, s["ents"][0], 1)


def test_two_sees_the_new_generation():
    t = tp.TwoPlay()
    c, f = reused_ledger()
    t._life = c
    s = {"f": f, "ents": [{"iid": 7, "type_key": "Song Heavy Sentry", "pos": [24.0, 7.45]}, rune(30.)]}
    c.update(f, s)
    assert tp.TwoPlay._rune_threats(t, f, s) == [(30. - R, 30. + R)]


def test_stab_sees_the_new_generation():
    cs = CS.CastStab()
    c, f = reused_ledger()
    cs._life = c
    s = {"f": f, "ents": [{"iid": 7, "type_key": "Song Heavy Sentry", "pos": [24.0, 7.45]}, rune(30.)]}
    c.update(f, s)
    assert cs._rune_threats(f, s) == [(30. - R, 30. + R)]


def test_the_low_hop_sees_the_new_generation():
    h = LH.RuneLowHop(two=True)
    c, f = reused_ledger()
    h._life = c
    s = {"f": f, "ents": [{"iid": 7, "type_key": "Song Heavy Sentry", "pos": [24.0, 7.45]}, rune(30.)]}
    c.update(f, s)
    assert h._rune_threats(f, s) == [(30. - R, 30. + R)]


# ---- slam_play: the way and the strike against the placed runes (any owner) ----

def slam_with(cx, circle_x, k, hx, born_ago=20, t_game=100.0, bombs=None):
    """A slam run in 'wait': its Clapper at cx, a circle first seen born_ago frames ago at circle_x."""
    p = sp.SlamPlay(sp.PlayCfg())
    p._life = RL.RuneCircles()
    f = 1000
    p._life.update(f - born_ago, st(f - born_ago, rune(circle_x)), t_game=t_game - born_ago * FT)
    p._life.update(f, st(f, rune(circle_x)), t_game=t_game)
    p._bombs = bombs
    s = state(f, "Slam Antic", 5 / 60., cx=cx, flip=False, hx=hx, ground=True)
    return p, s


def test_slam_walk_into_its_own_clappers_circle_is_declined():
    """Bout 30 (A2): the Clapper's own earlier circle is not exempt; she would be at the stand point inside it when it lights."""
    p, s = slam_with(cx=33.3, circle_x=32.4, k=5, hx=41.2, born_ago=42)
    tx = 33.3 - 5.0
    assert p._rune_path(s, tx, 5) == "circle"


def test_slam_declined_by_a_bomb_on_the_way():
    bk = np.array([[7., 38.0, 3.67, 2.166, 20., 28.]])
    p, s = slam_with(cx=33.3, circle_x=-40., k=5, hx=41.2, born_ago=0, bombs=bk)
    p._life = RL.RuneCircles()              # no circle
    assert p._rune_path(s, 33.3 - 5., 5) == "bomb"


def test_slam_is_not_declined_when_the_circle_burns_out_before_she_gets_there():
    p, s = slam_with(cx=33.3, circle_x=32.4, k=5, hx=47.0, born_ago=60)   # lights in 5 frames, she needs ~60 frames to get there
    assert p._rune_path(s, 33.3 - 5., 5) is None


def test_slam_keeps_a_stand_outside_every_circle():
    p, s = slam_with(cx=33.3, circle_x=10.0, k=5, hx=41.2, born_ago=20)
    assert p._rune_path(s, 33.3 - 5., 5) is None


def test_slam_walking_run_aborts_when_a_circle_comes_up():
    """The walk is checked every tick; a new circle over the stand ends the run."""
    p, s = slam_with(cx=33.3, circle_x=32.4, k=5, hx=41.2, born_ago=42)
    p.run = sp.Run(iid=7, fa=995, face=-1, ta=100.0 - 5 / 60., phase="walk", k_start=3, k_jump=None, hp0=9)
    m = p.step(1000, s, True, t_game=100.0, bombs=None)
    assert m is None and p.run is None and p.done[-1].phase == "abort" and "rune" in p.done[-1].why


# ---- the two integration points of the last check ----

def idle_hit_mask(monkeypatch):
    """The real TwoPlay IdleHit: the near one just went Slam Recover -> Idle in reach of the side slash (Sol's ROUTE_CHECK372 scene)."""
    monkeypatch.setattr(tp, "IDLEHIT", True)
    two = tp.TwoPlay()
    hx = 31.516
    m = None
    for f, st, age in ((1000, "Slam Recover", .3), (1001, "Idle", 0.)):
        s = two_state(f, st, age, hx=hx, cx=hx - 4, flip=True, facing=-1, b_x=46.)
        two.observe(f, s, f / 60.)
        m = two.step(f, s, True, True, 7, f / 60., two_enc=False)
    return two, m


def test_the_idlehit_side_slash_is_refused_when_it_takes_the_way_out(monkeypatch):
    from collections import Counter
    from ssbot.train import forum_planner_policy as FP
    two, m = idle_hit_mask(monkeypatch)
    assert m == kin.B_LEFT | kin.B_ATTACK and two.last_part == "idle"
    hx = 31.516
    S = kin.initial_state(PARAMS, hx, FLOOR + cs_.POS_DY, vy=0.0, facing=1, ground=True)
    pol = object.__new__(FP.ForumPlannerPolicy)
    pol._rune_tick = {"rows": bomb(30., 6., 14.), "sim": None, "ctx": (S, np.zeros(1, np.int64), kin.HoldState.idle(1), 1001, 1001)}
    pol.params, pol.terrain = PARAMS, TERR
    pol.counts = Counter()
    assert FP.ForumPlannerPolicy._rune_veto(pol, "two:idle", m) is True
    assert pol._rune_tick["last"]["who"] == "two:idle"


def test_the_slam_scripts_down_slash_is_exempt_only_for_its_owner():
    from collections import Counter
    from ssbot.train import forum_planner_policy as FP
    S = kin.initial_state(PARAMS, edge() - 0.9, FLOOR + cs_.POS_DY, vy=0.0, facing=1, ground=True)
    def veto(who, m):
        pol = object.__new__(FP.ForumPlannerPolicy)
        pol._rune_tick = {"rows": big(30., 10., 18.), "sim": None, "ctx": (S, np.zeros(1, np.int64), kin.HoldState.idle(1), 1000, 1000)}
        pol.params, pol.terrain = PARAMS, TERR
        pol.counts = Counter()
        return FP.ForumPlannerPolicy._rune_veto(pol, who, m)
    press = kin.B_DOWN | kin.B_ATTACK
    assert veto("slam", press) is False and veto("chase", L) is True
    assert veto("slam", L | kin.B_ATTACK) is True                 # (its side slash is an ordinary key)


def test_the_hook_path_check_counts_the_targets_own_small_runes():
    """The down slash and the hook are exempt from the last check only because their own path checks cover them: a placed small rune over the Clawline's way counts whoever cast it."""
    p = sp.SlamPlay()
    p.reset()
    r = NS(iid=7, ta=100.0)
    p._t = 100.0
    plan = NS(k_press=5, bb_press=1.0)
    hx, cx = 30.0, 38.0
    p._bombs = np.array([[7., hx, 4.6, 2.166, 0., 20.]])            # the target's own, over her now, on its frames
    assert p._cs_bomb(r, plan, cx, hx) is True
    p._bombs = np.array([[99., hx, 4.6, 2.166, 0., 20.]])           # the other one's
    assert p._cs_bomb(r, plan, cx, hx) is True
    p._bombs = np.array([[7., hx - 20., 4.6, 2.166, 0., 20.]])      # off her way
    assert p._cs_bomb(r, plan, cx, hx) is False
    p._bombs = np.array([[7., hx, 4.6, 2.166, 200., 220.]])         # long after the Clawline's window
    assert p._cs_bomb(r, plan, cx, hx) is False


def test_policy_veto_ends_the_script_and_counts():
    from collections import Counter
    from ssbot.train import forum_planner_policy as FP
    pol = object.__new__(FP.ForumPlannerPolicy)
    S = kin.initial_state(PARAMS, edge() - 0.9, FLOOR + cs_.POS_DY, vy=0.0, facing=1, ground=True)
    pol._rune_tick = {"rows": big(30., 10., 18.), "sim": None, "ctx": (S, np.zeros(1, np.int64), kin.HoldState.idle(1), 1000, 1000)}
    pol.params, pol.terrain = PARAMS, TERR
    pol.counts = Counter()
    assert FP.ForumPlannerPolicy._rune_veto(pol, "chase", L) is True
    assert pol.counts["rune_veto"] == 1 and pol.counts["rune_veto_chase"] == 1
    assert pol._rune_tick["last"]["who"] == "chase" and pol._rune_tick["last"]["veto"] is True
    assert FP.ForumPlannerPolicy._rune_veto(pol, "chase", R_) is False


def test_policy_without_runes_does_nothing():
    from collections import Counter
    from ssbot.train import forum_planner_policy as FP
    pol = object.__new__(FP.ForumPlannerPolicy)
    pol._rune_tick = {"rows": np.zeros((0, 6)), "sim": None, "ctx": None}
    pol.counts = Counter()
    assert FP.ForumPlannerPolicy._rune_veto(pol, "chase", L) is False
    assert pol.counts == Counter()


def test_a_circle_gone_while_lit_stops_counting():
    c = RL.RuneCircles()
    c.update(100, st(100, rune(30., True)))
    assert centres(c) == [30.]
    c.update(103, st(103))                   # not listed: still within ABSENT_F frames, no conclusion yet
    assert centres(c) == [30.]
    c.update(108, st(108))                   # gone for ABSENT_F frames: over
    c.update(109, st(109))
    assert c.spans() == []


def test_a_rune_lit_now_is_row_zero():
    c = RL.RuneCircles()
    c.update(200, st(200, rune(30., True)), t_game=200 * FT)
    r = c.rows()
    assert r.shape == (1, 6) and r[0, 4] == 0.0


def test_the_margin_counts_in_after_only():
    """Lit in 16 frames: after this step she could still run out at the last moment (out at frame 14), but not with the margin: refused."""
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), L, big(30., 16., 24.))
    assert veto and not info["after"] and info["now"]
    # no margin asked: nothing to refuse
    veto, info = RL.exit_veto(sim_for(edge() - 0.9), L, big(30., 16., 24.), m_big=0, m_bomb=0)
    assert not veto


def test_invulnerable_frames_do_not_count():
    box = np.tile(np.array([29.75, 3.0, 30.25, 5.1])[None, None, :], (1, 40, 1))
    rows = big(30., 5., 15.)
    ro = NS(box=box, flags=np.full((1, 40), kin.F_INVULN, np.int64))
    assert RL._safe(ro, rows, 0, 0, 0).all()
    ro = NS(box=box, flags=np.zeros((1, 40), np.int64))
    assert not RL._safe(ro, rows, 0, 0, 0).any()


# ---- slam_play.step: the start gate, the Clawline's circle gate ----

def test_slam_start_is_declined_through_step():
    """A live Run in wait: the start's own decision reads the rune path."""
    p, s = slam_with(cx=33.3, circle_x=32.4, k=5, hx=41.2, born_ago=42)
    s["ents"][0]["flipX"] = True            # facing her
    p.run = sp.Run(iid=7, fa=995, face=1, ta=100.0 - 5 / 60., phase="wait", k_start=None, k_jump=None, hp0=9)
    m = p.step(1000, s, True, t_game=100.0, bombs=None)
    assert m is None and p.run is not None and p.run.phase == "wait" and p.run.why == "circle"


def test_the_clawline_circle_gate_reads_the_ledger():
    p, s = slam_with(cx=30., circle_x=30., k=5, hx=20., born_ago=20)
    p._f = 1000
    assert p._cs_circle(s, 30., 20., 100.0) is True
    p, s = slam_with(cx=30., circle_x=30., k=5, hx=20., born_ago=20)
    p._f = 1000
    p._life = RL.RuneCircles()               # nothing placed
    assert p._cs_circle(s, 30., 20., 100.0) is False


# ---- the policy's last check, through the production arbitration statements (tests.test_b2_policy_priority) ----

def arb(veto_for, two=None):
    from collections import Counter
    from tests.test_b2_policy_priority import Script, selected, arbitration_code
    from ssbot.train import forum_planner_policy as mod
    p, res = selected(arm="A")
    p._rune_veto = lambda who, m: who == veto_for
    p.tac = None
    p.sc = NS(pq=None); p.pause_owned = False; p.m2 = None; p.wpress = None; p.air_show = None
    p._play_tick = None; p.v2feed = None; p.counts = Counter(); p._cogfly = lambda *a: None; p.cog = {"frames": set()}
    masks = {"slam": 16, "stab": 64, "low": 8, "chase": 128}
    order = ("slam", "stab", "low", "chase")
    live = None if veto_for not in order else order.index(veto_for)      # the scripts before the refused one have no key this tick
    def mk(name):
        return Script(mask=masks[name] if live is not None and order.index(name) >= live else None)
    p.slam_play = mk("slam"); p.claw = None; p.cast_stab = mk("stab")
    p.rune_lowhop = mk("low"); p.evade_chase = mk("chase")
    p.two = two; p._wake_f = None; p.enc = NS(name="w13")
    s = {"f": 2599, "hero": {}}
    scope = dict(self=p, res=res, r=NS(mask=None), s=s, raw=s, f=2599, fo=2599, tap=None, ws=NS(stamp=NS(t_game_s=1.), hero=NS(contact=NS(v="GROUND"))), S0=None,
                 prefix=[], hold=None, prefs=NS(target=7), esc_on=False, wt=None, fcast=None, m2_mask=None, b2_priority=None, b2_critical=None, air_tick=False)
    exec(arbitration_code(), mod.__dict__, scope)
    return p, scope


@pytest.mark.parametrize("who,attr,mask,next_own", [("slam", "slam_play", 16, "stab"), ("stab", "cast_stab", 64, "low"), ("low", "rune_lowhop", 8, "chase"), ("chase", "evade_chase", 128, "plan")])
def test_a_refused_script_ends_and_the_next_owner_takes_the_tick(who, attr, mask, next_own):
    p, out = arb(who)
    script = getattr(p, attr)
    assert script.aborted == ["rune exit"]
    assert out["own"] == next_own and (who != "slam" or out["play"] is not None)


def test_the_two_clapper_script_yields_when_refused():
    from ssbot.train import forum_planner_policy as mod
    class Two:
        last_part = "idle"; yielded = []
        manual_focus = False
        def step(self, *a, **k): return 1024
        def rune_yield(self, f): self.yielded.append(f)
        def asw_skip(self): return None
        def esc_yield(self, f, s=None): pass
    t = Two()
    p, out = arb("two:idle", two=t)
    assert t.yielded == [2599] and out["own"] == "plan"


def test_the_low_hops_check_reads_the_big_circles_only():
    from collections import Counter
    from ssbot.train import forum_planner_policy as FP
    pol = object.__new__(FP.ForumPlannerPolicy)
    S = kin.initial_state(PARAMS, 30.0, FLOOR + cs_.POS_DY, vy=0.0, facing=1, ground=True)
    pol._rune_tick = {"rows": bomb(30., 2., 9.), "sim": None, "ctx": (S, np.zeros(1, np.int64), kin.HoldState.idle(1), 1000, 1000)}
    pol.params, pol.terrain = PARAMS, TERR
    pol.counts = Counter()
    assert FP.ForumPlannerPolicy._rune_veto(pol, "low", L) is False and "last" not in pol._rune_tick


def chain_stub(rows, offer_mask, stage="active", commitment=None, run=None):
    from ssbot.combat import knife_chain_b2 as B2
    ch = object.__new__(B2.NativeChainB2)
    S = kin.initial_state(PARAMS, edge() - 0.9, FLOOR + cs_.POS_DY, vy=0.0, facing=1, ground=True)
    sim = ac.ChainSim(S, np.zeros(1, np.int64), kin.HoldState.idle(1), PARAMS, TERR, 1000, 1000)
    ch._context = ((1000, {}, 16.6, True, True), sim, None, None)
    ch.rune_rows = rows
    ch.commitment = commitment
    ch.runner = NS(run=run)
    ch.notes = []
    ch._note = lambda ev, **kw: ch.notes.append((ev, kw))
    calls = []
    ch._recover = lambda why, f: calls.append((why, f))
    ch.recovery = None
    return ch, NS(stage=stage, mask=offer_mask, move=None), calls


def test_chain_offer_refused_recovers_an_active_run():
    from ssbot.combat import knife_chain_b2 as B2
    ch, offer, calls = chain_stub(big(30., 10., 18.), L, run=NS(chain="rune_transfer"))
    out = B2.NativeChainB2._rune_gate(ch, offer)
    assert out is None and calls == [("rune exit gate: no way clear after this key", 1000)]
    assert ch.notes[0][0] == "b2_rune_exit_gate"


def test_chain_offer_passes_when_she_can_get_clear():
    from ssbot.combat import knife_chain_b2 as B2
    ch, offer, calls = chain_stub(big(30., 10., 18.), R_, run=NS(chain="rune_transfer"))
    assert B2.NativeChainB2._rune_gate(ch, offer) is offer and calls == []


def test_chain_down_slash_is_not_looked_at_side_slash_is():
    from ssbot.combat import knife_chain_b2 as B2
    ch, offer, calls = chain_stub(big(30., 10., 18.), kin.B_DOWN | kin.B_ATTACK, run=NS(chain="rune_transfer"))
    assert B2.NativeChainB2._rune_gate(ch, offer) is offer and calls == []
    ch, offer, calls = chain_stub(big(30., 10., 18.), L | kin.B_ATTACK, run=NS(chain="rune_transfer"))
    assert B2.NativeChainB2._rune_gate(ch, offer) is None and calls


def test_chain_recovery_release_is_not_looked_at():
    from ssbot.combat import knife_chain_b2 as B2
    ch, offer, calls = chain_stub(big(30., 10., 18.), 0, stage="recovery")
    assert B2.NativeChainB2._rune_gate(ch, offer) is offer and calls == []


def test_chain_without_rows_is_not_looked_at():
    from ssbot.combat import knife_chain_b2 as B2
    ch, offer, calls = chain_stub(None, L)
    assert B2.NativeChainB2._rune_gate(ch, offer) is offer and calls == []
