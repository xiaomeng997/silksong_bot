"""combat_run worker start: a game left in a cutscene (the post-kill memory scene after a CLEAR) is recognised, so the
worker loads the savestate instead of waiting for a main menu (gate run 20261002_150453 i3 timed out in load_slot)."""
from ssbot.probes.common import GS_PLAYING, MENU_MAIN, MENU_SAVE_PROFILES
from ssbot.tools.combat_run import _in_game_without_control


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
