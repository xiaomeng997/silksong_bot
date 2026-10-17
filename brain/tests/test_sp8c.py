"""Task 1v1 SP8c (forum.md 74): chase the Clapper's evade (SSBOT_FORUM_EVADE_CHASE, default off;
ssbot.combat.evade_chase)."""
import copy
import importlib

from ssbot.combat import evade_chase as ec
from ssbot.combat import slam_play as sp
from tests.test_slam_play import state


def ev_state(f, k, x_rel, cx=31.0, flip=False, ground=True, feet=0.0, atk_cd=0.0, dash_cd=0.0, clip="Idle",
             st=None, two=False, facing=None, ev=()):
    """Evade Scuttle at its frame k (st overrides the state); x_rel: her centre in front of its centre (u)."""
    face = 1 if flip else -1
    s = state(f, st or ec.EVADE, k / 60.0, cx=cx, flip=flip, hx=cx + face * x_rel, ground=ground)
    h = s["hero"]
    h["anim"] = {"clip": clip}
    h["box"][1] = 3.015 + feet
    h["tm"] = {"dash_cd": dash_cd, "atk_cd": atk_cd}
    h["facing"] = -face if facing is None else facing
    s["ents"][0]["vel"] = [0.0, 0.0]
    s["ev"] = list(ev)
    if two:
        o = copy.deepcopy(s["ents"][0])
        o["iid"] = 99
        o["pos"] = [cx + 15.0, 7.45]
        s["ents"].append(o)
    return s


def simulate(x0, land_k=0, cx=31.0, flip=False, n_ev=21, cfg=None, atk_cd0=0.3):
    """A toy evade: it slides EV_V per frame for n_ev frames away from her (its facing kept); she falls until land_k
    (no dash in the air), runs WALK_U with a key toward it, a dash tap moves her 28 u/s for 7 frames; the attack
    cooldown atk_cd0 s at the start. Returns (chase, [(k, x_rel, mask)])."""
    ch = ec.EvadeChase(cfg or ec.ChaseCfg())
    face = 1 if flip else -1
    toward = sp.M_R if -face > 0 else sp.M_L
    pending, out = {}, []
    x, c = x0, cx
    dash_from = None
    for k in range(0, n_ev + 4):
        f = 1000 + k
        m_now = pending.pop(f, 0)
        if m_now & sp.M_DASH and dash_from is None:
            dash_from = k
        if dash_from is not None and 1 <= k - dash_from <= ec.DASH_F:
            x -= ec.DASH_V / 60.0
        elif m_now & toward:
            x -= ec.WALK_U
        if k < n_ev:
            x += ec.EV_V
            c += -face * ec.EV_V
        st = ec.EVADE if k < n_ev else "Slam Antic"
        kk = k if k < n_ev else k - n_ev
        cd = max(0.0, atk_cd0 - k / 60.0)
        s = ev_state(f, kk, x, cx=c, flip=flip, ground=k >= land_k, feet=0.0 if k >= land_k else 2.0,
                     atk_cd=cd, st=st)
        m = ch.step(f, s, k >= land_k, True)
        out.append((k, round(x, 3), m))
        if m is not None:
            pending[f + ec.SEND_AHEAD] = m
    return ch, out


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_EVADE_CHASE", raising=False)
    monkeypatch.setenv("SSBOT_FORUM_V2", "1")
    try:
        assert not importlib.reload(ec).ENABLED
        monkeypatch.setenv("SSBOT_FORUM_EVADE_CHASE", "1")
        assert importlib.reload(ec).ENABLED
    finally:
        monkeypatch.delenv("SSBOT_FORUM_EVADE_CHASE", raising=False)
        monkeypatch.delenv("SSBOT_FORUM_V2", raising=False)
        importlib.reload(ec)


def test_no_start_outside_the_evade():
    ch = ec.EvadeChase()
    assert ch.step(1000, ev_state(1000, 5, 4.0, st="Idle"), True) is None
    assert ch.step(1001, ev_state(1001, 5, 4.0, st="Slam Antic"), True) is None
    assert ch.run is None and ch.n_evade == 0


def test_no_start_two_or_behind():
    ch = ec.EvadeChase()
    assert ch.step(1000, ev_state(1000, 0, 4.0, two=True), True) is None
    assert ch.why_not == {"two": 1}
    ch = ec.EvadeChase()
    assert ch.step(1000, ev_state(1000, 0, -2.0), True) is None
    assert ch.why_not == {"behind": 1}
    # one look per evade
    assert ch.step(1001, ev_state(1001, 1, -2.0), True) is None
    assert ch.n_evade == 1


def test_run_toward_and_close_at_the_end():
    for flip in (False, True):
        ch, out = simulate(4.0, land_k=9, flip=flip)
        toward = sp.M_R if flip is False else sp.M_L
        ms = [m for _, _, m in out if m is not None]
        assert ms[0] & toward and not ms[0] & sp.M_DASH        # in the air: the key toward it, no dash
        r = ch.done[0]
        assert r.phase == "done" and r.why == "end" and r.next_st == "Slam Antic"
        x_end = [x for k, x, _ in out if k == 20][0]
        assert x_end <= 8.0
        assert min(x for _, x, _ in out) >= ec.ChaseCfg().min_u - 0.05


def test_dash_when_far():
    ch, out = simulate(6.0, land_k=0)
    r = ch.done[0]
    assert r.dash_k is not None and r.dash_k <= 4
    assert min(x for _, x, _ in out) >= ec.ChaseCfg().min_u - 0.05
    x_end = [x for k, x, _ in out if k == 20][0]
    assert 4.0 <= x_end <= 6.5
    # the dash tap: two frames with the dash key, no attack within the dash
    dm = [k for k, _, m in out if m is not None and m & sp.M_DASH]
    assert len(dm) == 2 and dm[1] == dm[0] + 1
    am = [k for k, _, m in out if m is not None and m & sp.M_A]
    assert all(k - dm[0] >= ec.DASH_F + 2 for k in am)


def test_dash_only_past_dash_if_u():
    ch, out = simulate(3.6, land_k=0)
    r = ch.done[0]
    assert r.dash_k is None or r.dash_pred["d_run"] > ec.ChaseCfg().dash_if_u
    ch, out = simulate(3.6, land_k=0, cfg=ec.ChaseCfg(dash_if_u=8.0))
    assert ch.done[0].dash_k is None
    assert [x for k, x, _ in out if k == 20][0] <= 8.0


def test_no_dash_option():
    ch, out = simulate(6.0, land_k=0, cfg=ec.ChaseCfg(dash=0))
    assert ch.done[0].dash_k is None
    assert all(not (m or 0) & sp.M_DASH for _, _, m in out)


def test_slash_when_in_reach():
    ch, out = simulate(3.5, land_k=0, atk_cd0=0.0)
    r = ch.done[0]
    assert r.presses and r.presses[0][0] <= 3
    # two frames of the attack: one rising edge
    am = [k for k, _, m in out if m is not None and m & sp.M_A]
    assert am[:2] == [am[0], am[0] + 1]


def test_no_slash_out_of_reach():
    ch, out = simulate(7.5, land_k=0, atk_cd0=0.0, cfg=ec.ChaseCfg(dash=0))
    assert not ch.done[0].presses[:1] or ch.done[0].presses[0][1] <= 5.6


def test_wall_cuts_its_slide():
    # its back 1.34 u from its centre: facing left (flip False) it slides right toward WALL_R
    assert ec.slide_left(sp.WALL_R - 4.0, -1, 21) == 4.0 - 1.34
    assert abs(ec.slide_left(30.0, -1, 21) - 21 * ec.EV_V) < 1e-9
    assert ec.slide_left(30.0, -1, 0) == 0.0


def test_hurt_aborts():
    ch = ec.EvadeChase()
    assert ch.step(1000, ev_state(1000, 0, 4.0), True) is not None
    s = ev_state(1001, 1, 4.2)
    s["hero"]["health"] = 7
    assert ch.step(1001, s, True) is None
    assert ch.done[0].phase == "abort" and ch.done[0].why == "hurt"


def test_second_evade_new_run():
    ch = ec.EvadeChase()
    for k in range(0, 21):
        ch.step(1000 + k, ev_state(1000 + k, k, 4.0 + 0.1 * k), True)
    # it enters the slide again at once: a new run
    m = ch.step(1021, ev_state(1021, 0, 6.2), True)
    assert m is not None and len(ch.done) == 1 and ch.run is not None
    st = ch.stats()
    assert st["runs"] == 2 and st["evades"] == 2 and len(st["chase_runs"]) == 2
