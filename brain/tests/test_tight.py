"""SSBOT_FORUM_TIGHT (task precision push S5, forum.md §29.13): one switch for the push's candidate bundle (= the gate
config s4tb: RCLIP=2, REANCHOR=chain, RTHROW, PRESTRIKE, NSBOX=bin0, GATES, TINYCLIP, BODYCLIP); unset or empty
members get the bundle value, explicit ones keep theirs."""
import os
import subprocess
import sys

from ssbot.combat.multi_forecast import TIGHT_BUNDLE, apply_tight

S4TB = {"SSBOT_FORUM_RCLIP": "2", "SSBOT_FORUM_REANCHOR": "chain", "SSBOT_FORUM_RTHROW": "1",
        "SSBOT_FORUM_PRESTRIKE": "1", "SSBOT_FORUM_NSBOX": "bin0", "SSBOT_FORUM_GATES": "1",
        "SSBOT_FORUM_TINYCLIP": "1", "SSBOT_FORUM_BODYCLIP": "1"}


def test_bundle_is_s4tb():
    assert dict(TIGHT_BUNDLE) == S4TB


def test_off_sets_nothing():
    for v in (None, "", "0"):
        env = {} if v is None else {"SSBOT_FORUM_TIGHT": v}
        assert apply_tight(env) == []
        assert not any(k in env for k in S4TB)


def test_on_sets_every_unset_member_and_keeps_explicit_ones():
    env = {"SSBOT_FORUM_TIGHT": "1", "SSBOT_FORUM_BODYCLIP": "0", "SSBOT_FORUM_NSBOX": "", "SSBOT_FORUM_RCLIP": "1"}
    done = apply_tight(env)
    assert env["SSBOT_FORUM_BODYCLIP"] == "0" and env["SSBOT_FORUM_RCLIP"] == "1"
    assert env["SSBOT_FORUM_NSBOX"] == "bin0"
    assert set(done) == set(S4TB) - {"SSBOT_FORUM_BODYCLIP", "SSBOT_FORUM_RCLIP"}
    for k in done:
        assert env[k] == S4TB[k]


def test_module_flags_with_tight():
    """The module-level switches read after the bundle is applied (a fresh interpreter: they are read at import)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SSBOT_FORUM_")}
    env["SSBOT_FORUM_TIGHT"] = "1"
    code = ("import ssbot.combat.multi_forecast as m; "
            "print(m.REACH, m.REACH_HIT, m.PRESTRIKE, sorted(m.REANCHOR), m.RTHROW, m.TINYCLIP, m.BODYCLIP, "
            "sorted(m.NSBOX), m.GATES)")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).stdout.split("\n")[-2]
    assert out == "True True True ['chain'] True True True ['bin0'] True", out
