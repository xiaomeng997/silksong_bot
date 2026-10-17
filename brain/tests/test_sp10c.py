"""Task 1v1 SP10c (forum.md 81): SSBOT_FORUM_TWO_JUMPHIT - one Clapper jumps (J), L2's target is the other one (I) from
the first STATE of J's jump antic, IdleHit on I is not blocked by J's jump, and before J's landing she leaves its zone
(the landing hammer 0.67-7.76 u in front, its body behind; a jump cast's circle) by the exit that does not cross I's
body; default off (ssbot.combat.two_play, tactics.gauntlet, evade_chase)."""
import importlib

import pytest

from ssbot.combat import slam_play as sp
from ssbot.combat import two_play as tp
from tests.test_sp9 import two_state

J_X, H_X, I_X = 22.0, 31.0, 35.0          # J faces right (flipX), her 9 u in front of it, I 4 u past her facing left


def jstate(f, st, tin=0.0, hx=H_X, b_st="Idle", b_tin=0.1, ev=(), ground=True):
    s = two_state(f, st, tin, cx=J_X, flip=True, hx=hx, b_st=b_st, b_x=I_X, ground=ground, ev=ev)
    s["ents"][1]["fsms"] = [{"name": "Control", "state": b_st, "t": b_tin}]
    s["hero"]["can"] = {"dash": True}
    return s


@pytest.fixture
def on(monkeypatch):
    for k in ("JUMPHIT", "ANY", "IDLEHIT"):
        monkeypatch.setattr(tp, k, True)
    yield


def run(two, ss, focus=99):
    out = []
    for s in ss:
        two.observe(s["f"], s, s["f"] / 60.0)
        out.append(two.step(s["f"], s, sp.on_ground(s), True, focus, s["f"] / 60.0))
    return out


def test_default_off(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_TWO_JUMPHIT", raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        m = importlib.reload(tp)
        assert not m.JUMPHIT
        two = m.TwoPlay()
        run(two, [jstate(1000, "Idle", 0.5), jstate(1001, "Jump Antic")])
        assert two.jh is None and two.jh_view() is None and "jumphit" not in two.stats()
        monkeypatch.setenv("SSBOT_FORUM_TWO_JUMPHIT", "1")
        assert importlib.reload(tp).JUMPHIT
    finally:
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_TWO_JUMPHIT", raising=False)
        importlib.reload(tp)


def test_run_starts_on_the_antic_not_on_an_escape(on):
    two = tp.TwoPlay()
    run(two, [jstate(1000, "Idle", 0.5), jstate(1001, "Jump Antic", 1 / 60.0)])
    r = two.jh
    assert r is not None and r.J == 7 and r.I == 99 and r.kind == "jump" and r.f_a == 1000 and r.between
    v = two.jh_view()
    assert v["hold"] == 99 and v["phase"] == "hit" and not v["no_hit"]
    # the focus's escape jump at its wall (its back <= 6.2 u, her within 8.3 u and nearer it): SP9b's, no run
    two = tp.TwoPlay()
    ss = [two_state(f, st, 0.0, cx=tp.WALL_L + 4.0, flip=True, x_rel=4.0, b_x=40.0) for f, st in
          ((1000, "Idle"), (1001, "Jump Antic"))]
    run(two, ss)
    assert two.jh is None and two.jh_n["no_escape"] == 1


def test_idlehit_not_blocked_by_the_jump(on):
    two = tp.TwoPlay()
    hx = I_X - 2.9                                     # in the side slash's reach of I's body front (2.25 u)
    ss = [jstate(1000, "Idle", 0.5, hx=hx, b_st="Walk"), jstate(1001, "Jump Antic", 1 / 60.0, hx=hx, b_st="Idle",
                                                                b_tin=0.0)]
    s2 = jstate(1002, "Jump Antic", 2 / 60.0, hx=hx, b_st="Idle", b_tin=1 / 60.0)
    s2["hero"]["facing"] = 1                           # (the turn key on the entry)
    out = run(two, ss + [s2])
    assert out[1] == tp.M_R and out[2] & tp.M_A        # the press on I's Idle entry during J's antic
    tp.JUMPHIT = False                                   # (monkeypatch restores it)
    two = tp.TwoPlay()
    out = run(two, [jstate(1000, "Idle", 0.5, hx=hx, b_st="Walk"), jstate(1001, "Jump Antic", 1 / 60.0, hx=hx,
                                                                        b_st="Idle", b_tin=0.0)])
    assert out[-1] is None and two.idle.why == "other Jump Antic"


def test_leave_by_the_back_exit_before_the_landing(on):
    two = tp.TwoPlay()
    ss = [jstate(1000, "Idle", 0.5), jstate(1001, "Jump Antic", 1 / 60.0)]
    ss += [jstate(f, "Jump Antic", (f - 1000) / 60.0) for f in range(1002, 1030)]
    ss += [jstate(f, "Jump" if f < 1032 else "Air", (f - 1030) / 60.0) for f in range(1030, 1084)]
    phases, masks = [], []
    for s in ss:
        two.observe(s["f"], s, s["f"] / 60.0)
        masks.append(two.step(s["f"], s, sp.on_ground(s), True, 99, s["f"] / 60.0))
        phases.append(two.jh.phase if two.jh is not None else None)
    r = two.jh
    assert r.aim_hx == pytest.approx(H_X) and r.land == pytest.approx(J_X + 0.92 * (H_X - 5.0 - J_X))
    assert r.side == "back"                              # the front exit crosses I's body
    assert r.exit_x == pytest.approx(r.land - two.jcfg.back_u - 0.15)
    k = phases.index("leave")
    assert ss[k]["f"] - 1030 + tp.SEND_AHEAD >= r.f_leave - 1030 - 1 and ss[k]["f"] < 1030 + 55
    # the leave's keys: toward the exit (left), the turn first, then the dash held into the sprint
    m = [x for x in masks[k:] if x]
    assert m and all(x & tp.M_L for x in m) and any(x & tp.M_DASH for x in m)
    v = two.jh_view()
    assert v["phase"] == "leave" and v["no_hit"] == frozenset({7, 99}) and v["exit"] == r.exit_x
    # TWO_SPACE's stance (and the chase's block) follow the leave
    assert two.jh_block(1080) == "jh leave"


def test_gauntlet_targets_the_other(on, monkeypatch):
    from ssbot.combat.tactics import gauntlet as gt
    from tests.test_forum_l2 import l2
    tac = l2()
    tac.two_jh = {"J": 7, "I": 99, "phase": "hit", "hold": 99, "no_hit": frozenset(), "exit": None}

    class C:
        def __init__(self, iid, x):
            self.s = type("S", (), {"iid": iid, "family": gt.CC_IDLE, "type_key": gt.CLAPPER, "state": "Idle"})()
            self.x, self.d = x, abs(x - H_X)

    seen = {}
    monkeypatch.setattr(gt.GauntletTactics, "_goal", lambda self, ws, c, name, t, score, t_end=None, why="":
                        seen.update(target=c.s.iid, why=why) or seen)
    monkeypatch.setattr(gt.GauntletTactics, "_outer_room", lambda self, c, o: 5.0)
    tac._two_focus(None, [C(7, J_X), C(99, I_X)], 1.0, None)
    assert seen["target"] == 99 and seen["why"].startswith("two: jumphit hit")


# ---- SSBOT_FORUM_CLAW_CHASE (the late Clawline on a far jump) ----

def cstate(f, st, tin, hx=J_X + 10.0, b_st="Idle", y_air=0.0, clip="Idle", accepting=True, two=True, ev=(),
           ents=()):
    s = two_state(f, st, tin, cx=J_X, flip=True, hx=hx, b_st=b_st, b_x=44.0, ground=y_air <= 0.0, ev=ev)
    h = s["hero"]
    h["silk"], h["can"] = 3, {"harpoon": True, "dash": True}
    h["anim"] = {"clip": clip}
    h["hero_accepting_input"] = accepting
    if y_air > 0:
        h["box"] = [h["box"][0], h["box"][1] + y_air, h["box"][2], h["box"][3] + y_air]
    if not two:
        s["ents"] = s["ents"][:1]
    s["ents"] += list(ents)
    return s


def claw_on(monkeypatch, scope="any", var="A", cfg=""):
    from ssbot.combat import claw_chase as cc
    monkeypatch.setattr(cc, "ENABLED", True)
    monkeypatch.setattr(cc, "SCOPE", scope)
    monkeypatch.setattr(cc, "VARIANT", var)
    if cfg:
        monkeypatch.setenv("SSBOT_FORUM_CLAW_SET", cfg)
    return cc


def test_claw_default_off(monkeypatch):
    from ssbot.combat import claw_chase as cc
    monkeypatch.delenv("SSBOT_FORUM_CLAW_CHASE", raising=False)
    assert not importlib.reload(cc).ENABLED
    c = cc.ClawChase()
    assert c.step(1001, cstate(1001, "Jump Antic", 1 / 60.0), True, True) is None and c.run is None


def test_claw_sequence_any(monkeypatch):
    cc = claw_on(monkeypatch, "any", "A")
    c = cc.ClawChase(cc._cfg())
    out = {}
    f = 1000
    c.step(f, cstate(f, "Idle", 0.5), True, True)
    for f in range(1001, 1060):
        k = f - 1000
        st = "Jump Antic" if k < 30 else "Jump"
        k_mask = k + 2
        y = 1.0 if 4 <= k_mask < 30 else 0.0                       # in the air after the hop
        lock = 22 <= k_mask < 47
        clip = "Harpoon Dash" if lock else ("Recoil Twirl" if k_mask >= 47 else "Idle")
        m = c.step(f, cstate(f, st, (k if k < 30 else k - 30) / 60.0, y_air=max(y, 3.0 if k_mask >= 20 else y),
                             clip=clip, accepting=not lock), k_mask < 4, not lock)
        out[k_mask] = m
    r = c.run or (c.done[-1] if c.done else None)
    assert r is not None, dict(c.n)
    assert r.kind == "jump" and r.press_rel == -10 and r.k_press == 20 and r.k_hop == 3
    assert all(out[k] == cc.M_J for k in range(3, 13))           # the hop: 10 frames
    assert out[19] == cc.M_L                                     # the turn toward J (left of her)
    assert out[20] == out[21] == cc.M_CLAW | cc.M_L               # the press
    assert all(out[k] == 0 for k in range(22, 46))               # the lock
    assert r.k_ctrl is not None and any(out[k] == cc.M_DASH | cc.M_L for k in out if k >= 46)   # the air dash back


def test_claw_scope_bomb_gate(monkeypatch):
    cc = claw_on(monkeypatch, "bomb")
    c = cc.ClawChase(cc._cfg())
    c.step(1000, cstate(1000, "Idle", 0.5, two=False), True, True)
    c.step(1001, cstate(1001, "Jump Antic", 1 / 60.0, two=False), True, True)
    assert c.run is None and c.n["no_one"] == 1
    c = cc.ClawChase(cc._cfg())
    c.step(1000, cstate(1000, "Idle", 0.5), True, True)
    c.step(1001, cstate(1001, "Jump Antic", 1 / 60.0), True, True)
    assert c.run is None and c.n["no_no bomb"] == 1
    bomb = {"iid": 555, "type_key": "damager", "name": "rune bomb small", "colliders": [
        {"verts_world": [28.0, 3.0, 30.0, 3.0, 30.0, 5.0, 28.0, 5.0], "r": 2.166, "enabled": True, "damage": {"eff": 1}}]}
    c = cc.ClawChase(cc._cfg())
    c.step(1000, cstate(1000, "Idle", 0.5), True, True)
    c.step(1001, cstate(1001, "Jump Antic", 1 / 60.0, ents=(bomb,)), True, True)
    assert c.run is not None and c.run.why == "bomb"


def test_hit_script_walks_to_i_and_slashes(on):
    two = tp.TwoPlay()
    hx = I_X - 6.0                                     # out of the side slash's reach of I's body
    out = run(two, [jstate(1000, "Idle", 0.5, hx=hx), jstate(1001, "Jump Antic", 1 / 60.0, hx=hx)])
    assert two.jh.phase == "hit" and out[-1] == tp.M_R and two.last_part == "jh"     # the walk toward I
    s = jstate(1002, "Jump Antic", 2 / 60.0, hx=I_X - 2.9)
    s["hero"]["facing"] = 1
    m = run(two, [s])[0]
    assert m & tp.M_A and m & tp.M_R                   # the slash on I (in reach, facing it)
    s = jstate(1003, "Jump Antic", 3 / 60.0, hx=I_X - 2.9)
    s["hero"]["facing"] = 1
    assert run(two, [s])[0] == tp.M_A | tp.M_R           # the press's second frame
    two = tp.TwoPlay()
    two.jcfg.hit_script = 0
    run(two, [jstate(1000, "Idle", 0.5, hx=hx), jstate(1001, "Jump Antic", 1 / 60.0, hx=hx)])
    assert two.last_part != "jh"                       # t1 / t2: IdleHit and the planner


def test_claw_other_in_the_way(monkeypatch):
    cc = claw_on(monkeypatch, "any")
    c = cc.ClawChase(cc._cfg())
    # the other Clapper between her (J_X + 10) and J (J_X): no start
    s0, s1 = cstate(1000, "Idle", 0.5), cstate(1001, "Jump Antic", 1 / 60.0)
    for s in (s0, s1):
        s["ents"][1]["pos"] = [J_X + 5.0, 7.45]
    c.step(1000, s0, True, True)
    c.step(1001, s1, True, True)
    assert c.run is None and c.n["no_other in the way"] == 1
    c = cc.ClawChase(cc._cfg())                          # the other one behind her: the run starts
    c.step(1000, cstate(1000, "Idle", 0.5), True, True)
    c.step(1001, cstate(1001, "Jump Antic", 1 / 60.0), True, True)
    assert c.run is not None
