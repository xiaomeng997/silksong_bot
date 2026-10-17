"""Task 1v1 SP10a (forum.md 79): the cause audit - the policy's own_trace / slam_runs logging (decisions unchanged) and
ssbot.tools.sp10_audit's rules (who held the keys, the presses the cooldown dropped or delayed, the classification of an
HP loss)."""
from collections import Counter

from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from ssbot.tools import sp10_audit as au
from tests.test_sp9 import on, run, two_state  # noqa: F401 (the fixture)


def test_two_play_last_part(on):  # noqa: F811
    two = tp.TwoPlay()
    run(two, [two_state(1000, "Slam Recover", 0.3), two_state(1001, "Idle", 0.0)])
    assert two.last_part == "idle"                       # IdleHit's press on the Idle entry
    run(two, [two_state(1002, "Walk", 0.1, x_rel=20.0)])
    assert two.last_part is None


def test_slam_runs_rec():
    play = sp.SlamPlay()
    assert play.runs_rec() == []
    play.run = sp.Run(iid=7, fa=100, face=1, phase="wait", why="behind")
    rec = play.runs_rec()
    assert rec == [[7, 100, "wait", "behind", None, None, None, False, None, None, 0, ""]]
    assert "runs_rec" not in play.stats()                # the stats stay counters (the A/B tools sum them)


def _fr(f, m=0, acd=0.0, g=True, C=None, hx=20.0, clip="Idle", cd=True, late=0, hp_ev=()):
    return {"hx": hx, "hy": 4.57, "g": g, "clip": clip, "acd": acd, "dcd": 0.0, "cd": cd, "acc": True, "m": m,
            "late": late, "udt": 0.0167, "dt": 0.0167, "hp": 7, "vx": 0.0, "vy": 0.0, "C": C or {}, "hp_ev": list(hp_ev),
            "hit_ev": []}


def test_owner_exact_trace():
    pol = {"own_trace": [[100, "plan", None, 7, "RUSH", "two: keep; face"], [110, "slam", None, 7, "RUSH", "x"]]}
    o = au.Owner(pol, {})
    assert o.exact
    assert o.at(105)[0] == "plan" and o.at(112)[0] == "slam"     # frame x's keys came from the tick x - 2
    assert o.at(111)[0] == "plan" and o.at(101)[0] == "plan"


def test_presses_ok_delayed_dropped():
    fr = {}
    for f in range(100, 160):
        fr[f] = _fr(f)
    # an attack at 100 (the cooldown jumps up at 101), a press at 110 while cooling down that starts at its end (118),
    # a press at 140 while cooling down that never starts
    for f in range(101, 118):
        fr[f]["acd"] = 17.0 - (f - 101)
    fr[100]["m"] = au.A_BIT
    fr[110]["m"] = au.A_BIT
    for f in range(118, 135):
        fr[f]["acd"] = 17.0 - (f - 118)
    for f in range(136, 160):
        fr[f]["acd"] = 12.0
    fr[140]["m"] = au.A_BIT
    starts = au._attack_starts(fr)
    assert starts == {101, 118, 136}
    P = au._presses(fr, starts, au.Owner({"own_trace": [[0, "plan", None, None, None, None]]}, {}), 100, 159)
    assert [(p["f"], p["ok"], p["delayed"]) for p in P] == [(100, True, 0), (110, True, 8.0), (140, False, 0)]


def _ep(fr, hits_src, own_trace, slam_runs=None, f_wake=0, fk=10 ** 9):
    pol = {"own_trace": own_trace, "slam_runs": slam_runs or []}
    owner = au.Owner(pol, {})
    starts = au._attack_starts(fr)
    ep = {"fr": fr, "owner": owner, "dec": {}, "dec_f": [], "starts": starts, "fk": fk, "f_wake": f_wake,
          "slam_runs": slam_runs or [], "slam_runs_known": True, "landed": [], "pol": pol}
    ep["presses"] = au._presses(fr, starts, owner, 0, fk)
    return ep


def test_hit_classes_planner_moved_in_and_handoff():
    # F (iid 7) at x 30 facing left (her side), B (iid 9) at 40; she walks left into F's body: the planner moved in
    fr = {}
    for f in range(900, 1001):
        hx = 34.0 - 0.1 * (f - 960) if f >= 960 else 34.0
        C = {7: ("Idle", 0.5, 30.0, 7.45, -1, 200, (28.7, 31.3)), 9: ("Idle", 0.5, 40.0, 7.45, -1, 200, (38.7, 41.3))}
        fr[f] = _fr(f, m=au.L_BIT if f >= 958 else 0, C=C, hx=hx)
    fr[1000]["hp_ev"] = [(2, "Wave 14 - Finale/Song Heavy Sentry (2)")]
    ep = _ep(fr, None, [[0, "plan", None, 7, "RUSH", "two: keep; face"]])
    h = au._hp_losses(ep)[0]
    assert h["by"] == 7 and h["src"] == "body" and h["moved_in"]
    assert h["cat"] == au.L2 and h["sub"].startswith("planner moved into it")
    # the second hammer: B's slam began while the playbook ran F's slam (no run for B's): the hand-off
    fr2 = {}
    for f in range(700, 1001):
        stb = "Slam Antic" if 940 <= f < 990 else "Slam 1" if f >= 990 else "Idle"
        C = {7: ("Slam Recover", 0.3, 30.0, 7.45, -1, 200, (28.7, 31.3)), 9: (stb, 0.1, 40.0, 7.45, -1, 200, (38.7, 41.3))}
        fr2[f] = _fr(f, C=C, hx=35.0, g=False, cd=True)
    fr2[1000]["hp_ev"] = [(2, "Song Heavy Sentry (3)/Slam Collider 1")]
    runs = [[7, 860, "done", "landed", 3, 26, 47, True, 49, None, 104, "two"]]
    ep2 = _ep(fr2, None, [[0, "plan", None, 9, "RUSH", "two: keep; face"]], slam_runs=runs)
    h2 = au._hp_losses(ep2)[0]
    assert h2["by"] == 9 and h2["src"] == "hammer" and h2["move"] == "Slam Antic"
    assert h2["cat"] == au.SCR and "hand-off" in h2["sub"]


def test_hit_classes_stall_first():
    fr = {}
    for f in range(900, 1001):
        C = {7: ("Idle", 0.5, 30.0, 7.45, -1, 200, (28.7, 31.3))}
        fr[f] = _fr(f, C=C, hx=31.0, late=4 if f == 990 else 0)
    fr[1000]["hp_ev"] = [(2, "Wave 14 - Finale/Song Heavy Sentry (2)")]
    h = au._hp_losses(_ep(fr, None, [[0, "plan", None, 7, "RUSH", "x"]]))[0]
    assert h["cat"] == au.HOST


def test_summary_tables():
    items = [{"cat": au.L2, "sub": "a", "ep": "e1", "f": 1}, {"cat": au.L2, "sub": "a", "ep": "e1", "f": 2},
             {"cat": None, "sub": "", "ep": "e1", "f": 3}]
    assert Counter((x["cat"], x["sub"]) for x in items if x["cat"]) == Counter({(au.L2, "a"): 2})
