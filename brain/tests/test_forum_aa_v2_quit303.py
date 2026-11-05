"""Task 179 #303 (live 179-L1 w13_walk179_20261105T222716Z_8f9e9629): verify_episode's cheat check after a real quit.

Live: Quit_To_Menu at 2966 with the hero loaded and HP read, then the hero None and no game for 2967..3001: there is no
cheat status to read. The raw HP audit already proved that unload (real_quit_unload 2967..3002, complete). Those
frames are reported, not waived; every other missing status or cheat still fails.
"""
import pytest

from ssbot.tools.forum_aa_v2 import cheat_scan
from ssbot.train.forum_measure_metrics import audit_states


def fight(f, scene="Hang_04", paused=False, cheat=0, **hero):
    return {"f": f, "dt": .1, "hero": {"health": 7, "health_blue": 0, **hero}, "ev": [], "ents": [],
            "game": {"scene": scene, "paused": paused, "cheat": cheat}}


def unloaded(f, game=None):
    return {"f": f, "dt": .1, "hero": None, "ev": [], "game": game, "ents": []}


def quit_rows():
    return [fight(9), fight(10), fight(11), fight(12, paused=True), fight(13, scene="Quit_To_Menu", paused=True),
            unloaded(14), unloaded(15), unloaded(16, {"scene": "Menu_Title", "paused": False})]


def scan(rows):
    return cheat_scan(rows, audit_states(rows, wake_f=10, end_f=16))


def test_the_proven_unload_has_no_status_to_read():
    assert scan(quit_rows()) == (None, [14, 15, 16])


def _missing_before_quit(rows):
    rows[2] = dict(fight(11), game={"scene": "Hang_04", "paused": False})


def _cheat_before_quit(rows):
    rows[2] = fight(11, cheat=1)


def _invincible_before_quit(rows):
    rows[2] = fight(11, is_invincible=True)


def _quit_only_requested(rows):
    rows[4] = fight(13, paused=True)  # no Quit_To_Menu scene: no proven unload


def _cheat_reported_after_quit(rows):
    rows[7] = unloaded(16, {"scene": "Menu_Title", "paused": False, "cheat": 1})


def _hero_back_after_unload(rows):
    rows[7] = fight(16)


def _gameplay_scene_without_hero(rows):
    rows[6] = unloaded(15, {"scene": "Bonetown", "paused": False})


def _missing_past_the_boundary(rows):
    rows.append(unloaded(17))


@pytest.mark.parametrize("fault", [_missing_before_quit, _cheat_before_quit, _invincible_before_quit,
                                   _quit_only_requested, _cheat_reported_after_quit, _hero_back_after_unload,
                                   _gameplay_scene_without_hero, _missing_past_the_boundary])
def test_every_other_missing_status_or_cheat_still_fails(fault):
    rows = quit_rows()
    fault(rows)
    error, _ = scan(rows)
    assert error == "cheat or missing cheat status"


def test_the_boundary_needs_a_complete_audit():
    metrics = dict(audit_states(quit_rows(), wake_f=10, end_f=16), complete=False)
    assert cheat_scan(quit_rows(), metrics)[0] == "cheat or missing cheat status"
    assert cheat_scan(quit_rows(), {})[0] == "cheat or missing cheat status"
