"""Early focus switch: uncertain input must not advertise a dash/sprint approach."""
from types import SimpleNamespace as NS

import pytest

from ssbot.combat.tactics import gauntlet as G
from ssbot.core.worldstate import E


def world(*, can=True, cd=0.0, cd_conf=1.0, contact="GROUND", contact_conf=1.0):
    return NS(hero=NS(can={"dash": can}, dash_cd_left=E(cd, conf=cd_conf),
                      contact=E(contact, conf=contact_conf)))


@pytest.mark.parametrize("can,cd,expected", [(True, 0.0, 0.0), (False, .19, .19), (True, -.001, 0.0)])
def test_known_ground_dash_wait(can, cd, expected):
    assert G.GauntletTactics._two_dash_wait(world(can=can, cd=cd)) == expected


@pytest.mark.parametrize("changes", [
    {"can": None}, {"can": "false"}, {"can": 1}, {"can": False},
    {"cd": float("nan")}, {"cd": float("inf")}, {"cd": "0"}, {"cd": True},
    {"cd_conf": float("nan")}, {"cd_conf": float("inf")}, {"cd_conf": .79},
    {"contact": "AIR"}, {"contact_conf": 0.0}, {"contact_conf": float("nan")},
])
def test_unknown_or_unavailable_dash_does_not_claim_approach(changes):
    assert G.GauntletTactics._two_dash_wait(world(**changes)) is None


@pytest.mark.parametrize("state,expected", [
    ("Evade Scuttle", False), ("Slam 2", False), ("Slam Recover", False), ("Cast 2", False),
    ("Slam Antic", True), ("Spell Antic", True), ("Cast Slam Antic", True),
])
def test_buddy_attack_phase_not_entire_committed_move(state, expected):
    subject = NS(type_key=G.CLAPPER, iid=1, alive=True, in_play=True, state=state, committed=True)
    assert G.GauntletTactics._buddy_locked(NS(subjects=[subject]), 2) is expected
    assert not G.GauntletTactics._buddy_locked(NS(subjects=[subject]), 1)


def test_nominal_approach_estimate_includes_key_delay_and_cooldown():
    # A tactical ETA only: the planner still checks the actual selected path.
    assert G.GauntletTactics._two_sprint_s(0.0, .19) == 0.0
    assert G.GauntletTactics._two_sprint_s(13.391, .1916697174) == pytest.approx(.82217, abs=.0001)


def focus_probe(monkeypatch, enabled, open_x, wall_x, *, arena=(14.6, 48.4)):
    """Exercise real focus arbitration; the stance/arrival calculation is outside this priority regression."""
    monkeypatch.setattr(G, "TWO_SPRINTSW", enabled)
    monkeypatch.setattr(G.two_play, "SPACE", True)
    t = G.GauntletTactics.__new__(G.GauntletTactics)
    t.pb = NS(arena_x=arena)
    t.stats, t.rune = {}, {}
    t.two_esc = t.two_pm = t.two_jh = t._jt = None
    t._wall_sw = t._sw_why = None
    t._two_run_ok = lambda *args: (False, "other free")
    t._goal = lambda ws, c, name, now, score, **kw: G.Goal(name, c.s.iid, c.x, now, why=kw["why"])
    a = G.Cand(NS(iid=1, family=G.CC_IDLE), open_x, 7.0, 1.0, open_x, 0.0)
    b = G.Cand(NS(iid=2, family=G.CC_SLAM, state="Slam Antic"), wall_x, 7.0, 2.0, wall_x, 0.0)
    return t, [a, b], G.Goal(G.RUSH, 1, open_x, 0.0)


@pytest.mark.parametrize("enabled,open_x,wall_x,arena,target,skipped", [
    (True, 27.866, 20.096, (14.6, 48.4), 1, 2),  # live f3499: wall room5.50
    (True, 26.326, 15.432, (14.6, 48.4), 1, 2),  # live f3660: wall room0.83
    (False, 27.866, 20.096, (14.6, 48.4), 2, None),
    (False, 26.326, 15.432, (14.6, 48.4), 2, None),
    (True, 30.786, 31.455, (14.6, 48.4), 2, None),  # live f3027: open slammer
    (True, 36.674, 47.568, (14.6, 48.4), 1, 2),  # mirrored wall
    (True, 27.0, 20.50, (14.5, 48.5), 1, 2),  # existing band includes6.0
    (True, 27.0, 20.501, (14.5, 48.5), 2, None),
    (True, 13.5, 5.5, (0.0, 20.0), 2, None),  # exactly1u is not more room
    (True, 13.49, 5.5, (0.0, 20.0), 1, 2),
])
def test_wall_preference_precedes_legacy_slammer(monkeypatch, enabled, open_x, wall_x, arena, target, skipped):
    t, candidates, old = focus_probe(monkeypatch, enabled, open_x, wall_x, arena=arena)
    goal = t._two_focus(None, candidates, 1.0, old)
    assert goal.target == target
    assert t._wall_sw == skipped  # same no_hit / LOW / SLAM skip output, not only target display


def test_explicit_escape_hold_stays_above_wall_preference(monkeypatch):
    t, candidates, old = focus_probe(monkeypatch, True, 27.866, 20.096)
    monkeypatch.setattr(G.two_play, "ESC", True)
    t.two_esc = {"after_land": False}
    escape = G.Goal(G.RUSH, 2, 20.096, 1.0, why="explicit escape hold")
    t._esc_hold = lambda *args: escape
    assert t._two_focus(None, candidates, 1.0, old) is escape
    assert t._wall_sw is None
