"""Task 1v1 SP8b (forum.md 73): the jump slam's antic far away - dash, stop, one side slash (SSBOT_FORUM_JB_SLAM_DASH) - and
the jump moves at a wall (SSBOT_FORUM_JB_CORNER: walk in, slash through the antic, the walk under), both default off
(ssbot.combat.cast_stab, combat.jump_behind, gauntlet)."""
import importlib

import pytest

from ssbot.combat import cast_stab as cs
from ssbot.combat import jump_behind as jb
from ssbot.combat import slam_play as sp
from tests.test_cast_stab import antic_state
from tests.test_slam_play import state
from tests.test_sp8 import hero


def jump_antic_state(f, k, x0, cx=31.0, flip=False, ground=True, ev=(), facing=None):
    """The jump slam's antic at frame k (Jump Antic 0..29, then Jump)."""
    st, tin = ("Jump Antic", k / 60.0) if k < 30 else ("Jump", (k - 30) / 60.0)
    face = 1 if flip else -1
    s = state(f, st, tin, cx=cx, flip=flip, hx=cx + face * x0, ground=ground)
    s["hero"]["tm"] = {"dash_cd": 0.0, "atk_cd": 0.0}
    s["ev"] = list(ev)
    if facing is not None:
        s["hero"]["facing"] = facing
    return s


def test_off_by_default(monkeypatch):
    for k in ("SSBOT_FORUM_JB_SLAM_DASH", "SSBOT_FORUM_JB_CORNER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        importlib.reload(jb)
        m = importlib.reload(cs)
        assert not m.SLAM_DASH and not m.CORNER and not jb.CORNER
        monkeypatch.setenv("SSBOT_FORUM_JB_SLAM_DASH", "1")
        monkeypatch.setenv("SSBOT_FORUM_JB_CORNER", "1")
        importlib.reload(jb)
        m = importlib.reload(cs)
        assert m.SLAM_DASH and m.CORNER and m.ENABLED
        monkeypatch.setenv("SSBOT_FORUM_JUMP_BEHIND", "0")       # the corner only with JUMP_BEHIND
        importlib.reload(jb)
        assert not importlib.reload(cs).CORNER
    finally:
        for k in ("SSBOT_FORUM_JB_SLAM_DASH", "SSBOT_FORUM_JB_CORNER", "SSBOT_FORUM_JUMP_BEHIND", "SSBOT_FORUM_V2"):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(jb)
        importlib.reload(cs)


def test_no_jump_start_with_the_switches_off():
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, slam_dash=False, corner=False)
    assert c.step(1000, hero(jump_antic_state(1000, 2, 9.4)), True, t_game=1000 / 60) is None
    assert c.run is None and c.n_jantic == 0


def test_jump_stop_plan():
    c = cs.StabCfg()
    p = cs.stop_plan(9.4, c, stop_u=c.j_stop_u, stop_lo=c.j_stop_lo)
    assert not p["tap"] and c.j_stop_lo <= p["x_stop"] <= c.j_stop_u
    p = cs.stop_plan(7.2, c, stop_u=c.j_stop_u, stop_lo=c.j_stop_lo)
    assert p["tap"]
    # the cast's numbers unchanged without the keywords
    assert cs.stop_plan(9.5, c) == cs.stop_plan(9.5, c, stop_u=c.stop_u, stop_lo=c.stop_lo)


def run_jump_stop(flip, x0, slam_dash=True, corner=False, cx=31.0, facing=None):
    """A toy jump slam antic: she moves 28 u/s in the dash, then the sprint, stops dead on the release; a walk key moves
    her WALK_U; each landed slash (standing reach 4.67 u) knocks it 0.48 u away."""
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, slam_dash=slam_dash, corner=corner)
    face = 1 if flip else -1
    toward = sp.M_R if -face > 0 else sp.M_L
    hx = cx + face * x0
    keys, j0, rel, hits = {}, None, None, 0
    for k in range(0, 40):
        f = 1000 + k
        m_now = keys.get(k, 0)
        j = None if j0 is None else k - j0
        moving = rel is None and j is not None and j >= 1 and c.done + [c.run] and \
            (c.done + [c.run])[0] is not None and not (c.done + [c.run])[0].walk
        v = 0.0
        if moving:
            v = cs.DASH_V if j <= cs.DASH_F else max(cs.SPRINT_V, cs.DASH_V - cs.SPRINT_DEC * (j - cs.DASH_F))
            hx -= face * v / 60.0
            if not m_now & sp.M_DASH and j >= cs.DASH_F:
                rel = k
        elif m_now & toward:
            hx -= face * sp.WALK_U
        clip = "Dash" if moving and j <= cs.DASH_F else "Sprint" if moving else "Idle"
        ev = []
        if m_now & sp.M_A and not keys.get(k - 1, 0) & sp.M_A and (hx - cx) * face <= 4.67 and k < 31:
            ev = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "src": "Slash"}}]
            hits += 1
            cx -= face * 0.48
        s = jump_antic_state(f, k, (hx - cx) * face, cx=cx, flip=flip, ev=ev, facing=facing)
        hero(s, clip, vx=-face * v)
        if facing is not None:
            s["hero"]["facing"] = facing
        m = c.step(f, s, True, True, t_game=f / 60.0)
        if m is not None:
            keys[k + 2] = m
            j0 = k + 2 if j0 is None else j0
    return c, keys, hits, toward


@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("x0", [7.2, 9.4, 10.6])
def test_the_jump_stop(flip, x0):
    c, keys, hits, toward = run_jump_stop(flip, x0)
    r = (c.done + [c.run])[0]
    assert r.kind == "jump" and r.mode == "stop" and not r.walk and r.rel_j is not None
    assert 3.4 <= r.x_stop <= 4.67
    assert len(r.presses) == 1 and r.presses[0] <= c.cfg.j_press_k_max and hits == 1
    assert keys[round(r.presses[0])] == sp.M_A                 # the first press after a dash: no direction key
    assert r.phase == "done" and r.why == "last press"         # the planner from the press's second frame on
    st = c.stats()
    assert st["j_stops"] == 1 and st["j_antics"] == 1 and st.get("stops", 0) == 0


@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("x0,n", [(5.6, 1), (4.9, 2)])
def test_the_jump_walk_in(flip, x0, n):
    # below the dash band she walks in and slashes; twice when the first press comes by antic frame 7
    face = 1 if flip else -1
    c, keys, hits, toward = run_jump_stop(flip, x0, facing=float(-face))
    r = (c.done + [c.run])[0]
    assert r.walk and r.kind == "jump" and r.rel_j is None
    assert len(r.presses) == n and hits == n and all(b - a >= c.cfg.slash_cd for a, b in zip(r.presses, r.presses[1:]))
    assert all(keys[round(p)] & sp.M_A and keys[round(p)] & toward for p in r.presses)
    assert not any(m & sp.M_DASH for m in keys.values())


def test_the_jump_walk_in_turns_first():
    # she faces away: the key toward it on the frame before the first press
    c, keys, hits, toward = run_jump_stop(False, 4.3, facing=-1.0)       # it faces left (-1), she is on its left
    r = (c.done + [c.run])[0]
    p0 = round(r.presses[0])
    assert keys[p0 - 1] & toward and keys[p0] & sp.M_A


def test_jump_no_start():
    c = cs.CastStab(slam_dash=True, corner=False, stop=False, dash_slash=False)
    assert c.step(1000, hero(jump_antic_state(1000, 2, 12.5)), True, t_game=1000 / 60) is None      # too far
    assert c.step(1100, hero(jump_antic_state(1100, 2, 3.0)), True, t_game=1100 / 60) is None       # at its body
    assert c.step(1200, hero(jump_antic_state(1200, 16, 9.4)), True, t_game=1200 / 60) is None      # late
    st = c.stats()
    assert st["no_j_distance"] == 1 and st["no_j_near"] == 1 and st["no_j_late"] == 1


def test_jump_one_clapper_only():
    c = cs.CastStab(slam_dash=True, corner=True)
    s = hero(jump_antic_state(1000, 2, 9.4))
    e2 = dict(s["ents"][0])
    e2["iid"], e2["pos"] = 8, [44.0, 7.45]
    s["ents"].append(e2)
    assert c.step(1000, s, True, t_game=1000 / 60) is None and c.run is None


def test_the_jump_stab_variant():
    cfg = cs.StabCfg()
    cfg.j_mode = 1
    c = cs.CastStab(cfg, slam_dash=True, corner=False, stop=False, dash_slash=False)
    m = c.step(1000, hero(jump_antic_state(1000, 0, 10.0)), True, t_game=1000 / 60)
    assert m is not None and m & sp.M_DASH and c.run.mode == "stab" and c.run.kind == "jump"
    assert c.run.pred["x_aim"] >= cfg.j_aim_x_min and c.run.pred["hit"] + c.run.k0 < cs.J_AIM_K
    # the crouched body front: the hit later than in the cast antic
    assert cs.stab_path(10.0, front=cs.J_BODY_FRONT)["hit"] >= cs.stab_path(10.0)["hit"]


# ---- JB_CORNER ----

@pytest.mark.parametrize("flip", [False, True])
def test_corner_jump_slam(flip):
    # its centre 2.5 u from the wall behind it, she 4.3 u in front (in reach): two slashes in the jump slam's antic
    face = 1 if flip else -1
    cx = (sp.WALL_L + 2.5) if flip else (sp.WALL_R - 2.5)
    c, keys, hits, toward = run_jump_stop(flip, 4.3, slam_dash=False, corner=True, cx=cx, facing=float(-face))
    r = (c.done + [c.run])[0]
    assert r.corner and r.walk and r.kind == "jump" and r.pred["room0"] == pytest.approx(2.5, abs=0.01)
    assert len(r.presses) == 2 and hits == 2
    assert c.stats()["corner_stops"] == 1


def test_corner_not_at_a_wall():
    # 6 u from the wall: not a corner; with JB_SLAM_DASH off nothing starts in the jump slam's antic
    c = cs.CastStab(slam_dash=False, corner=True)
    cx = sp.WALL_R - 6.0
    assert c.step(1000, hero(jump_antic_state(1000, 2, 4.3, cx=cx)), True, t_game=1000 / 60) is None
    assert c.stats()["no_j_off"] == 1


def test_corner_far_goes_to_the_dash():
    # at a wall but 9.4 u away: beyond the walk-in, the dash-stop (JB_SLAM_DASH) takes it
    c = cs.CastStab(slam_dash=True, corner=True)
    cx = sp.WALL_R - 2.5
    m = c.step(1000, hero(jump_antic_state(1000, 2, 9.4, cx=cx)), True, t_game=1000 / 60)
    assert m is not None and m & sp.M_DASH and not c.run.corner and c.run.kind == "jump"


def test_corner_jump_cast():
    # the jump cast at a wall, she 5.5 u away (below T2's band): walk in and slash; T2 / T1 unchanged elsewhere
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, corner=True)
    cx = sp.WALL_R - 3.0
    m = c.step(1000, hero(antic_state(1000, 2, 5.5, cx=cx)), True, t_game=1000 / 60)
    assert c.run is not None and c.run.corner and c.run.kind == "cast" and c.run.phase == "slash"
    assert m is not None and not m & sp.M_DASH
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, corner=True)
    c.step(1000, hero(antic_state(1000, 2, 7.6, cx=cx)), True, t_game=1000 / 60)
    assert c.run.mode == "stop" and not c.run.corner and not c.run.walk          # T2 as before


def test_corner_cast_identity_off():
    # the corner off: the jump cast's antic at a wall exactly as SP8a (no start at 5.5 u: below every band)
    c = cs.CastStab(dash_slash=True, combo=True, stop=True, corner=False)
    cx = sp.WALL_R - 3.0
    assert c.step(1000, hero(antic_state(1000, 2, 5.5, cx=cx)), True, t_game=1000 / 60) is None
    assert c.stats()["no_distance"] == 1


def test_walk_fits_corner_end():
    c = jb.CFG
    # 3 u from the landing's front side to behind it: 3 + 1.87 = 4.87 u, 35 frames of walk
    assert jb.walk_fits(10.0, 7.0, 1, 0.0, end_f=38) and not jb.walk_fits(10.0, 7.0, 1, 10.0, end_f=38)
    assert jb.corner_room(jb.WALL_L + 2.0, 1) == pytest.approx(2.0) and jb.corner_room(jb.WALL_R - 3.0, -1) == \
        pytest.approx(3.0)
    assert c["corner_walk_end_f"] < c["walk_end_f"]
