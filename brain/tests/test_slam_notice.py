"""Task 182 package 1 shadow (SSBOT_FORUM_SLAM_NOTICE; the person 11-12 "做吧"): the slam playbook link's hand-back notice,
predicted and logged only (combat.slam_notice). The rise below is a real catch of package 0's repeat 50 (episode 4, the press at
15036, the live hero of the full-episode replay pkg1/r/r2_ep4_P0): DownSlash, the bounce's hold (vy reads 17.4 and -10
alternately), the decaying rise with its duplicate STATEs, the apex at 15064."""
from types import SimpleNamespace as NS

import pytest

from ssbot.combat import slam_notice as sn

# frame: (y, vy, clip) from the recording (press at 15036; contact = the first DownSpikeBounce frame is 15046 here: Recoil Twirl
# 15042-15045 holds the bounce)
REAL = {15036: (8.99, -0.52, "Airborne"), 15037: (8.956, -1.72, "Airborne"), 15038: (8.956, -1.72, "DownSlashAlt"),
        15039: (8.897, -2.92, "DownSlashAlt"), 15040: (8.815, -4.12, "DownSlashAlt"), 15041: (8.708, -5.32, "DownSlashAlt"),
        15042: (8.578, -10.0, "Recoil Twirl"), 15043: (8.926, 17.4, "Recoil Twirl"), 15044: (8.926, 17.4, "Recoil Twirl"),
        15045: (9.274, -10.0, "Recoil Twirl"), 15046: (9.622, 17.4, "DownSpikeBounce 1"),
        15047: (9.946, 16.2, "DownSpikeBounce 1"), 15048: (10.246, 15.0, "DownSpikeBounce 1"),
        15049: (10.522, 13.8, "DownSpikeBounce 1"), 15050: (10.522, 13.8, "DownSpikeBounce 1"),
        15051: (10.774, 12.6, "DownSpikeBounce 1"), 15052: (11.002, 11.4, "DownSpikeBounce 1"),
        15053: (11.206, 10.2, "DownSpikeBounce 1"), 15054: (11.386, 9.0, "DownSpikeBounce 1"),
        15055: (11.542, 7.8, "DownSpikeBounce 1"), 15056: (11.542, 7.8, "DownSpikeBounce 1"),
        15057: (11.674, 6.6, "DownSpikeBounce 1"), 15058: (11.782, 5.4, "DownSpikeBounce 1"),
        15059: (11.866, 4.2, "DownSpikeBounce 1"), 15060: (11.926, 3.0, "DownSpikeBounce 1"),
        15061: (11.962, 1.8, "DownSpikeBounce 1"), 15062: (11.962, 1.8, "DownSpikeBounce 1"),
        15063: (11.974, 0.6, "DownSpikeBounce 1"), 15064: (11.962, -0.6, "DownSpikeBounce 1")}


def state(f, x=30.0, vx=0.0):
    y, vy, clip = REAL[f]
    return {"f": f, "hero": {"pos": [x, y], "box": [x - 0.23, y - 1.553, x + 0.23, y + 0.522], "vel": [vx, vy],
                             "anim": {"clip": clip}}}


def run_catch(owner_after=15042):
    n = sn.ApexNotice()
    run = NS(iid=7, fa=14990, k_press=None)
    for f in sorted(REAL):
        if f == 15036:
            run.k_press = 47                         # the tick that sends the press
        live = run if f < owner_after else None      # bounce_tail takes the keys at the bounce (the run ends)
        n.observe(f, state(f), live, "slam" if live is not None else "chain")
    return n


def test_a_real_catch_is_predicted_and_observed():
    n = run_catch()
    assert len(n.rows) == 1
    r = n.rows[0]
    assert r["end"] == "apex" and r["press_f"] == 15036 and r["contact_f"] == 15046 and r["rise_f"] == 15047
    assert r["apex"][0] == 15064 and r["apex"][4] == "chain"
    tags = [p[4] for p in r["preds"]]
    assert tags[0] == "press" and tags[1] == "contact" and set(tags[2:]) == {"rise"}
    press, contact = r["preds"][0], r["preds"][1]
    assert press[1] == 15036 + sn.PRESS_TO_APEX and contact[1] == 15046 + sn.CONTACT_TO_APEX
    # the notice: the first prediction within 3 frames of its apex, the owner of that tick
    nf, napex = r["notice"][0], r["notice"][1]
    assert napex - nf <= sn.NOTICE_F and r["notice"][-1] == "chain"
    assert abs(napex - r["apex"][0]) <= 2                 # the rise's prediction lands within 2 frames of the real apex
    assert abs(r["notice"][3] - r["apex"][2]) < 0.3       # and its height within 0.3 u


def test_a_run_living_on_past_its_apex_gets_no_second_row():
    # the playbook's own way out keeps the run after the apex (no bounce_tail hand-off): one row, never reopened
    n = run_catch(owner_after=10 ** 9)
    run = NS(iid=7, fa=14990, k_press=47)
    for f in range(15065, 15080):
        n.observe(f, {"f": f, "hero": {"pos": [30.0, 11.9], "vel": [0.0, -2.0], "anim": {"clip": "DownSpikeBounce 1"}}}, run,
                  "slam")
    assert len(n.rows) == 1 and n._cur is None and n.rows[0]["apex"][4] == "slam"


def test_the_rise_frames():
    assert sn.rise_frames(17.4) == 17 and sn.rise_frames(1.2) == 2 and sn.rise_frames(0.6) == 1


def test_no_contact_ends_the_row():
    n = sn.ApexNotice()
    run = NS(iid=7, fa=1000, k_press=47)
    for f in range(2000, 2000 + sn.CONTACT_WAIT + 3):
        n.observe(f, {"f": f, "hero": {"pos": [30.0, 8.0], "vel": [0.0, -5.0], "anim": {"clip": "DownSlashAlt"}}}, run, "slam")
    assert [r["end"] for r in n.rows] == ["no contact"] and n.rows[0]["apex"] is None


def test_a_dash_ending_the_rise_is_the_observed_apex_with_its_clip():
    n = sn.ApexNotice()
    run = NS(iid=7, fa=14990, k_press=None)
    for f in sorted(REAL):
        if f == 15036:
            run.k_press = 47
        s = state(f)
        if f == 15055:
            s["hero"]["vel"][1] = -1.2
            s["hero"]["anim"]["clip"] = "Air Dash"
        n.observe(f, s, run, "plan")
        if n.rows:
            break
    assert n.rows[0]["apex"][0] == 15055 and n.rows[0]["apex"][3] == "Air Dash"


def test_a_new_run_closes_the_old_row():
    n = sn.ApexNotice()
    a = NS(iid=7, fa=1000, k_press=47)
    b = NS(iid=8, fa=1100, k_press=47)
    n.observe(1045, {"f": 1045, "hero": {"pos": [30.0, 9.0], "vel": [0.0, -1.0], "anim": {"clip": "Airborne"}}}, a, "slam")
    n.observe(1145, {"f": 1145, "hero": {"pos": [30.0, 9.0], "vel": [0.0, -1.0], "anim": {"clip": "Airborne"}}}, b, "slam")
    assert [r["end"] for r in n.rows] == ["next run"] and n._cur["iid"] == 8


# ---- Sol REVIEW397: the summary keeps a row still open at the episode end, marked incomplete, never given an apex ----

def feed_until(last, run=None):
    n = sn.ApexNotice()
    run = run or NS(iid=7, fa=14990, k_press=None)
    for f in sorted(REAL):
        if f > last:
            break
        if f == 15036:
            run.k_press = 47
        n.observe(f, state(f), run if f < 15042 else None, "slam" if f < 15042 else "chain")
    return n


def counts_add_up(s):
    return s["opened"] == s["completed"] + s["incomplete"] == len(s["rows"])


def test_an_episode_ending_right_after_the_press_keeps_the_row_incomplete():
    n = feed_until(15036)
    s = n.summary()
    assert (s["opened"], s["completed"], s["incomplete"]) == (1, 0, 1) and counts_add_up(s)
    r = s["rows"][0]
    assert r["complete"] is False and r["end"].startswith("incomplete") and r["apex"] is None and r["notice"] is None
    assert r["press_f"] == 15036 and [p[4] for p in r["preds"]] == ["press"] and "key" not in r
    # read only: a second read is the same, the open row itself is unchanged and nothing moved into rows
    assert n.summary() == s and n.rows == [] and n._cur["end"] is None and "complete" not in n._cur


def test_an_episode_ending_after_the_notice_before_the_apex_keeps_the_notice():
    n = feed_until(15062)                          # the notice is out (apex predicted within 3 frames), the apex (15064) not yet
    s = n.summary()
    assert (s["opened"], s["completed"], s["incomplete"]) == (1, 0, 1) and counts_add_up(s)
    r = s["rows"][0]
    assert r["notice"] is not None and r["notice"][-1] == "chain" and r["apex"] is None and r["complete"] is False
    assert r["end"].startswith("incomplete")


def test_completed_rows_stay_with_an_open_one():
    n = run_catch()                                # one catch to its apex
    n.observe(16000, {"f": 16000, "hero": {"pos": [30.0, 9.0], "vel": [0.0, -1.0], "anim": {"clip": "Airborne"}}},
              NS(iid=8, fa=15955, k_press=47), "slam")
    s = n.summary()
    assert (s["opened"], s["completed"], s["incomplete"]) == (2, 1, 1) and counts_add_up(s)
    assert [r["complete"] for r in s["rows"]] == [True, False] and s["rows"][0]["end"] == "apex"
    assert s["rows"][0]["apex"][0] == 15064 and s["rows"][1]["apex"] is None


def test_reset_isolates_the_next_episode():
    n = feed_until(15040)
    assert n.summary()["incomplete"] == 1
    n.reset()
    assert n.summary() == {"opened": 0, "completed": 0, "incomplete": 0, "rows": []}


def test_the_policy_summary_reads_summary_whenever_the_switch_is_on():
    import ast
    import inspect
    import textwrap
    from ssbot.train import forum_planner_policy as mod
    src = textwrap.dedent(inspect.getsource(mod.ForumPlannerPolicy.stats))
    calls = {ast.unparse(n.func) for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)}
    assert "self.slam_notice.summary" in calls and "slam_notice.rows" not in src


def test_switch_follows_v2(monkeypatch):
    import importlib
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    monkeypatch.delenv("SSBOT_FORUM_SLAM_NOTICE", raising=False)
    m = importlib.reload(sn)
    try:
        assert m.ENABLED is True
        monkeypatch.setenv("SSBOT_FORUM_SLAM_NOTICE", "0")
        assert importlib.reload(sn).ENABLED is False
    finally:
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_SLAM_NOTICE", raising=False)
        importlib.reload(sn)
