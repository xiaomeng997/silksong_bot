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
