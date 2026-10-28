import json

import pytest

from ssbot.tools.forum_measure_replay import h2_environment


ARM = dict(SSBOT_FORUM_V2="1", SSBOT_FORUM_V2_EVERY="1", SSBOT_FORUM_V2_CORNER="13",
           SSBOT_FORUM_RUNE_NOPRE="1", SSBOT_FORUM_RUNE_BOMB="1", SSBOT_FORUM_RUNE_HOP="1",
           SSBOT_FORUM_NOGLIDE="1", SSBOT_FORUM_RUNE_FACE="3", SSBOT_FORUM_SLAM_PLAY="1",
           SSBOT_FORUM_JUMP_BEHIND="1", SSBOT_FORUM_HERO2="1")


def test_arm_without_launchers_common_environment_is_rejected():
    with pytest.raises(ValueError):
        h2_environment(json.dumps({"env": ARM}).encode())


def test_all_three_common_settings_are_required_and_preserved():
    env = {**ARM, "SSBOT_FORUM_FR": "seen_cf", "SSBOT_FORUM_REACT": "escape+n+g", "SSBOT_FORUM_MARGIN": "state"}
    assert h2_environment(json.dumps({"env": env}).encode()) == env
    for key in ("SSBOT_FORUM_FR", "SSBOT_FORUM_REACT", "SSBOT_FORUM_MARGIN"):
        with pytest.raises(ValueError):
            h2_environment(json.dumps({"env": {k: v for k, v in env.items() if k != key}}).encode())
