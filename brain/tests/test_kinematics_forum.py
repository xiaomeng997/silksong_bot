"""Forum loadout rules of the compiled rollout (ssbot.knowledge.kin_jit "Forum loadout"): the decompiled behaviour of
wall slide, cling, wall jump, glide, dash and the Reaper down slash in a box room, and that the Hunter parameters
(abilities 0) never enter the new modes."""
import numpy as np
import pytest

from ssbot.knowledge import kinematics as km

L, R, J, A, D, U, DASH = km.B_LEFT, km.B_RIGHT, km.B_JUMP, km.B_ATTACK, km.B_DOWN, km.B_UP, km.B_DASH
ALL = (km.AB_WALL | km.AB_CLING | km.AB_DASH | km.AB_BROLLY | km.AB_RPR_DOWN | km.AB_WALLSLASH_SLOW |
       km.AB_HARD_LAND)


@pytest.fixture(scope="module")
def params():
    p = km.HeroParams.load()
    return km.HeroParams.from_json(p.to_json() | {"abilities": ALL, "attack_cooldown": 0.5, "attack_recovery": 0.3})


@pytest.fixture(scope="module")
def room():
    # floor y 0 over x -5..40, a wall solid x -5..0 up to y 30 (its face at x 0), a ceiling at y 40
    return km.Terrain2D.from_boxes([(-5, -5, 40, 0), (-5, 0, 0, 30), (-5, 40, 40, 45)])


def _roll(p, terr, S, m):
    return km.rollout(S, np.asarray(m, dtype=np.int64)[None], p, terr)


def _in_air_at_wall(p, terr, hold: int):
    """Jump into the wall at x 0 from x 2 holding left, then hold left `hold` frames."""
    S = km.initial_state(p, 2.0, p.skin + p.foot, facing=-1)
    m = [J | L] * 24 + [L] * hold
    return S, m


def test_slide_then_cling_holds_height(params, room):
    S, m = _in_air_at_wall(params, room, 90)
    r = _roll(params, room, S, m)
    assert r.final[km.WSIDE, 0] == -1 and r.final[km.CLING, 0] == 1
    box = r.box[0]
    assert abs(box[-1, 0] - params.skin) < 1e-6             # pressed against the face, skin off it
    assert np.ptp(box[-30:, 1]) < 1e-6                         # Ascendant's Grip: no sliding while holding in


def test_release_slides_after_the_stick_time(params, room):
    S, m = _in_air_at_wall(params, room, 60)
    m = m + [0] * 30
    r = _roll(params, room, S, m)
    y = r.box[0, :, 1]
    t0 = len(m) - 30
    assert np.ptp(y[t0:t0 + 9]) < 1e-6                         # WALLSLIDE_STICK_TIME 0.15 s: 9 frames still
    assert y[-1] < y[t0] - 0.1                                 # then down the wall
    assert r.final[km.WSIDE, 0] == -1 and r.final[km.CLING, 0] == 0


def test_wall_jump_kicks_off_and_locks(params, room):
    S, m = _in_air_at_wall(params, room, 40)
    m = m + [J] * 16
    r = _roll(params, room, S, m)
    t0 = len(m) - 16
    vx = r.vel[0, t0 + 1:t0 + 10, 0]
    assert vx.max() > 20 and (vx >= 0).all()                  # WJ_KICKOFF_SPEED 25 away from the wall
    assert r.box[0, -1, 0] > 2.0 and r.box[0, -1, 1] > r.box[0, t0, 1]
    assert r.final[km.WSIDE, 0] == 0


def test_wall_scramble_climbs(params, room):
    S, m = _in_air_at_wall(params, room, 40)
    r0 = _roll(params, room, S, m)
    m = m + [DASH | L] * 6 + [L] * 60
    r = _roll(params, room, S, m)
    assert (r.mode[0] == km.M_SCRAMBLE).any()
    y0 = r0.box[0, -1, 1]
    rise = r.box[0, :, 1].max() - y0
    assert 2.5 < rise < 6.0                                    # 22 u/s up against 48-72 u/s^2: about 3.4-5 u
    assert r.final[km.WSIDE, 0] == -1                          # back to the wall slide (To Wall Slide)


def test_glide_approaches_float_speed(params, room):
    S = km.initial_state(params, 10.0, params.skin + params.foot)
    m = [J] * 12 + [0] * 4 + [J] * 120
    r = _roll(params, room, S, m)
    g = np.flatnonzero(r.mode[0] == km.M_GLIDE)
    assert len(g) > 40 and g[0] < 25
    assert r.vel[0, g, 1].min() == pytest.approx(params.glide_vy, abs=0.2)   # Float Idle AccelerateToY -6
    p0 = km.HeroParams.load()
    r0 = _roll(p0, room, km.initial_state(p0, 10.0, p0.skin + p0.foot), m)
    assert not np.isin(r0.mode[0], (km.M_GLIDE, km.M_DASH, km.M_SPRINT, km.M_RPR_DS, km.M_HARD_LAND)).any()


def test_ground_dash_speed_and_air_sprint(params, room):
    S = km.initial_state(params, 10.0, params.skin + params.foot)
    r = _roll(params, room, S, [DASH | R] * 3 + [0] * 30)
    vx = r.vel[0, :, 0]
    assert vx.max() == pytest.approx(params.dash_speed)
    S2 = km.initial_state(params, 10.0, params.skin + params.foot)
    r2 = _roll(params, room, S2, [J] * 10 + [DASH | R] * 30 + [0] * 10)
    assert (r2.mode[0] == km.M_SPRINT).any()


def test_tracker_matches_the_batch_estimator_with_the_forum_rows(params):
    """StateTracker (the planner's per-tick state) and state_table give the same rows, the Forum ones included, on a
    synthetic log: a jump into a wall, slide, cling, wall jump, a glide's phases, a dash, a Reaper down slash."""
    from tests.test_kinematics import REST, _state
    seq = []
    for i in range(70):
        fl, clip, hs, rel, wall = {"onGround": i < 5}, "Idle", 1, False, [False, False]
        if 5 <= i < 10:
            fl["jumping"] = True
        if 10 <= i < 25:
            fl.update(wallSliding=True, wallClinging=12 <= i < 18)
            wall = [True, False]
        if 25 <= i < 30:
            fl["jumping"] = True                       # off the wall: a wall jump
        if 32 <= i < 45:
            clip = ("Umbrella Inflate Antic" if i < 35 else "Umbrella Inflate" if i < 38 else "Umbrella Float"
                    if i < 43 else "Umbrella Deflate")
            hs, rel = 7, True
        if 47 <= i < 50:
            fl["dashing"] = True
        if 55 <= i < 64:
            clip = "v3 Down Slash Antic" if i < 58 else "v3 Down Slash" if i < 61 else "Fall"
            hs, rel = 7, True
        s = _state(i, 10.0 + 0.05 * i, REST + (1.0 if i >= 5 else 0.0), **fl)
        s["hero"] = dict(s["hero"], anim={"clip": clip}, hero_state=hs, control_relinquished=rel, wall=wall,
                         vel=[0.0, -1.0 if 10 <= i < 25 else 0.0])
        s["fs"] = int(i % 6 != 0)
        seq.append(s)
    tr = km.Trace.from_states(seq, params)
    modes = km.classify_modes(tr, forum=True)
    assert set(modes[32:45]) == {km.M_GLIDE} and set(modes[47:50]) == {km.M_DASH} and \
        set(modes[55:64]) == {km.M_RPR_DS}
    ref = km.estimate_state(tr, np.arange(len(tr)), params)
    assert ref[km.WSIDE, 15] == -1 and ref[km.CLING, 15] == 1 and ref[km.WLOCK, 26] >= 0
    assert ref[km.PHASE, 40] == 2 and ref[km.PHASE, 44] == 3
    trk = km.StateTracker(params)
    for i, s in enumerate(seq):
        trk.push(s)
        same = (trk.S == ref[:, i]) | (np.isnan(trk.S) & np.isnan(ref[:, i]))
        assert same.all(), (i, [km.ROW_NAMES[j] for j in np.flatnonzero(~same)])


def test_reaper_down_slash_lunges_forward_down(params, room):
    S = km.initial_state(params, 10.0, 15.0, facing=1, ground=False)
    r = _roll(params, room, S, [A | D] * 3 + [0] * 40)
    md = r.mode[0]
    assert (md == km.M_RPR_DS).any()
    k = np.flatnonzero(md == km.M_RPR_DS)
    assert r.vel[0, k, 0].max() > 10                           # Rpr Downslash: 30 forward, decaying x0.7
    assert (r.vel[0, k, 1] <= 1e-9).all()
    assert md[-1] == km.M_NORMAL                               # control back after Fall 2


@pytest.fixture(scope="module")
def thunk_params(params):
    d = params.to_json() | {"abilities": ALL | km.AB_THUNK | km.AB_SLOPES, "crest": "Reaper"}
    return km.HeroParams.from_json(d).with_slash_polys()


def test_side_slash_into_a_wall_recoils_once(thunk_params, room):
    # standing 2.5 u from the wall face (x 0), facing it: the Reaper slash (reach 3.6 u past the box centre) meets it
    p = thunk_params
    S = km.initial_state(p, 2.5, p.skin + p.foot, facing=-1)
    r = _roll(p, room, S, [L | A] + [0] * 20)
    x = r.box[0, :, 0]
    assert x[-1] > x[0] + 0.4                                  # pushed away from the wall (8 recoil steps x 3.75)
    k_on = int(np.flatnonzero(r.vel[0, :, 0] > 1.0)[0])
    assert 5 <= k_on <= 7                                      # the collider's first active step (live 5 / 6 / 7)
    # out of reach: no recoil
    S = km.initial_state(p, 4.5, p.skin + p.foot, facing=-1)
    r = _roll(p, room, S, [A] + [0] * 20)
    assert np.ptp(r.box[0, :, 0]) < 1e-6
    # the Hunter rules (no AB_THUNK) never recoil off terrain
    S = km.initial_state(p, 2.5, p.skin + p.foot, facing=-1)
    q = km.HeroParams.from_json(p.to_json() | {"abilities": ALL})
    r = _roll(q, room, S, [A] + [0] * 20)
    assert np.ptp(r.box[0, :, 0]) < 1e-6


def test_alt_attack_alternates_and_resets(thunk_params, room):
    p = thunk_params
    S = km.initial_state(p, 20.0, p.skin + p.foot, facing=1)
    m = [A] + [0] * 39 + [A] + [0] * 39 + [U | A] + [0] * 60 + [A] + [0] * 5
    r = km.rollout(S, np.asarray(m, dtype=np.int64)[None], p, room, lanes=True)
    kinds = r.final[km.ATK_KIND, 0]
    # normal (sets altAttack) -> alt (clears it) -> up (a new direction clears, then sets it) -> after > 0.8 s a
    # normal again (the reset)
    assert kinds == 1.0


def test_jump_under_a_sloped_ceiling_slides_along_it(thunk_params):
    # a 45 deg ceiling edge from (0, 4) up to (6, 10), the solid above-left of it: a jump under it slides up and right
    # along it (the velocity's part into the edge projected away) instead of passing through (the Hunter rules do not
    # collide slopes)
    p = thunk_params
    outline = np.array([[-5.0, 4.0], [0.0, 4.0], [6.0, 10.0], [-5.0, 10.0]])
    floor = np.array([[-5.0, -5.0], [30.0, -5.0], [30.0, 0.0], [-5.0, 0.0]])
    terr = km.Terrain2D.from_outlines([outline, floor], closed=[True, True])
    assert len(terr.slopes) == 1
    S = km.initial_state(p, 2.0, p.skin + p.foot, facing=1)
    r = _roll(p, terr, S, [J] * 20)
    top = r.box[0, :, 3]
    xc = 0.5 * (r.box[0, :, 0] + r.box[0, :, 2])
    edge_y = 4.0 + (r.box[0, :, 0] - 0.0)                      # the edge's height over the box's left side
    assert (top <= edge_y + 1e-3).all()                        # never through the edge
    assert xc[-1] > 2.0 + 0.1                                  # along the edge, away from the solid
    q = km.HeroParams.from_json(p.to_json() | {"abilities": ALL})
    r2 = _roll(q, terr, S, [J] * 20)
    assert r2.box[0, :, 3].max() > top.max() + 0.5            # without AB_SLOPES the jump goes through
