"""combat_run worker start: a game left in a cutscene (the post-kill memory scene after a CLEAR) is recognised, so the
worker loads the savestate instead of waiting for a main menu (gate run 20261002_150453 i3 timed out in load_slot)."""
from datetime import datetime

from ssbot.probes.common import GS_PLAYING, MENU_MAIN, MENU_SAVE_PROFILES
from ssbot.tools.combat_run import _in_game_without_control, new_run_dir


def test_cutscene_is_a_game_without_control():
    hero = {"hero_accepting_input": False}
    assert _in_game_without_control({"game": {"scene": "Memory_Silk_Heart", "gs": GS_PLAYING, "menu": 0}, "hero": hero,
                                     "pause": {}})
    # gameplay, the title and the save select are not
    ok = {"hero_accepting_input": True}
    assert not _in_game_without_control({"game": {"scene": "Bone_05", "gs": GS_PLAYING, "menu": 0}, "hero": ok,
                                         "pause": {}})
    assert not _in_game_without_control({"game": {"scene": "Menu_Title", "gs": 1, "menu": MENU_MAIN}, "hero": None})
    assert not _in_game_without_control({"game": {"scene": "Menu_Title", "gs": 1, "menu": MENU_SAVE_PROFILES},
                                         "hero": hero})
    # a new game started from the save select: PLAYING in Tut_01 with the menu state still SAVE_PROFILES
    assert _in_game_without_control({"game": {"scene": "Tut_01", "gs": GS_PLAYING, "menu": MENU_SAVE_PROFILES},
                                     "hero": hero, "pause": {}})

def test_run_dirs_started_in_the_same_second_get_distinct_names(tmp_path):
    """Two runs of one encounter and tag started in the same second (FileExistsError, 2026-10-03 07:45): the second
    gets a numeric suffix; the first keeps the plain <timestamp>_<encounter>_<tag> name."""
    now = datetime(2026, 10, 3, 7, 45, 0)
    a = new_run_dir("BellBeast", "eval_planner_oracle", root=tmp_path, now=now)
    b = new_run_dir("BellBeast", "eval_planner_oracle", root=tmp_path, now=now)
    c = new_run_dir("BellBeast", "eval_planner_oracle", root=tmp_path, now=now)
    assert a.name == "20261003_074500_BellBeast_eval_planner_oracle"
    assert b.name == a.name + "_2" and c.name == a.name + "_3"
    assert a.is_dir() and b.is_dir() and c.is_dir()
