"""Task 178 pre-live: after a real quit to menu the hero is unloaded; those frames have no HP to read.

Live e390 (Quit_To_Menu 3555, hero None 3556..3591, Menu_Title 3592) and e4 (2987, 2988..3023, 3024) failed the raw
full-window audit on exactly those frames. Every other missing HP still fails.
"""
import pytest
from ssbot.train.forum_measure_metrics import audit_states


def fight(f, hp=7, scene="Hang_04", paused=False, events=()):
    return {"f": f, "dt": .1, "hero": {"health": hp, "health_blue": 0}, "ev": list(events),
            "game": {"scene": scene, "paused": paused}, "ents": []}


def unloaded(f, game=None, events=()):
    return {"f": f, "dt": .1, "hero": None, "ev": list(events), "game": game, "ents": []}


def quit_rows():
    return [fight(9), fight(10), fight(11), fight(12, paused=True), fight(13, scene="Quit_To_Menu", paused=True),
            unloaded(14), unloaded(15), unloaded(16, {"scene": "Menu_Title", "paused": False})]


def test_real_quit_unload_frames_have_no_hp_to_read_and_keep_their_time():
    a = audit_states(quit_rows(), wake_f=10, end_f=16)
    assert a["complete"] and a["problems"] == []
    assert a["real_quit_unload"] == {"quit_scene_f": 13, "first_f": 14, "last_f": 16, "frames": 3}
    assert a["T"] == pytest.approx(.7) and a["L"] == 0  # the window and its time are unchanged


def _no_hp_while_fighting(rows):
    rows[2] = fight(11, hp=None)


def _quit_keys_but_no_quit_scene(rows):
    rows[4] = fight(13, paused=True)  # paused gameplay scene: the quit was only requested


def _unexpected_scene_after_quit(rows):
    rows[6] = unloaded(15, {"scene": "Bonetown", "paused": False})


def _hp_event_after_unload(rows):
    rows[6] = unloaded(15, events=[{"f": 15, "k": "hp", "q": 1, "d": {"delta": -1, "blue_delta": 0}}])


def _hero_back_after_unload(rows):
    rows[7] = fight(16)


def _hero_field_missing(rows):
    rows[5] = {k: v for k, v in unloaded(14).items() if k != "hero"}


@pytest.mark.parametrize("fault,problem", [
    (_no_hp_while_fighting, "missing health snapshot"),
    (_quit_keys_but_no_quit_scene, "missing health snapshot"),
    (_unexpected_scene_after_quit, "missing health snapshot"),
    (_hp_event_after_unload, "hp event after real-quit unload"),
    (_hero_back_after_unload, "hero or gameplay scene after real-quit unload"),
    (_hero_field_missing, "missing health snapshot"),
])
def test_every_other_missing_or_unloaded_hp_still_fails(fault, problem):
    rows = quit_rows();fault(rows)
    a = audit_states(rows, wake_f=10, end_f=16)
    assert not a["complete"] and problem in a["problems"]
