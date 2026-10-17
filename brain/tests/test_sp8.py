"""Task 1v1 SP8a (forum.md 72): the jump cast's antic far away - the DashStab + RecoilStab (SSBOT_FORUM_JB_DASH_COMBO)
and dash, stop, side slashes (SSBOT_FORUM_JB_DASH_STOP), both default off (ssbot.combat.cast_stab); the SP6 model's
fixes (its body front in the cast antic, the dash's frames, gravity)."""
import importlib

import numpy as np
import pytest

from ssbot.combat import cast_stab as cs
from ssbot.combat import slam_play as sp
from ssbot.knowledge import kinematics as kin
from tests.test_cast_stab import antic_state


def test_switches_follow_v2(monkeypatch):
    keys = ("SSBOT_FORUM_JB_DASH_SLASH", "SSBOT_FORUM_JB_DASH_COMBO", "SSBOT_FORUM_JB_DASH_STOP", "SSBOT_FORUM_V2")
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    try:
        m = importlib.reload(cs)
        assert not (m.ENABLED or m.COMBO or m.STOP)              # without v2: off
        monkeypatch.setenv("SSBOT_FORUM_V2", "1")
        m = importlib.reload(cs)
        assert m.ENABLED and m.DASH_SLASH and m.COMBO and m.STOP  # the SP8a default with v2
        monkeypatch.setenv("SSBOT_FORUM_JB_DASH_SLASH", "0")
        m = importlib.reload(cs)
        assert m.ENABLED and m.STOP and not m.DASH_SLASH and not m.COMBO   # COMBO only with JB_DASH_SLASH
        monkeypatch.setenv("SSBOT_FORUM_JB_DASH_STOP", "0")
        m = importlib.reload(cs)
        assert not (m.ENABLED or m.COMBO or m.STOP)              # arm rnsp8a0
        monkeypatch.setenv("SSBOT_FORUM_V2", "0")
        monkeypatch.setenv("SSBOT_FORUM_JB_DASH_STOP", "1")
        m = importlib.reload(cs)
        assert m.ENABLED and m.STOP and not m.DASH_SLASH
    finally:
        for k in keys:
            monkeypatch.delenv(k, raising=False)
        importlib.reload(cs)


@pytest.mark.parametrize("d0,j_live", [(11.41, 15), (11.51, 15), (10.26, 15), (10.27, 16), (10.14, 16),
                                       (10.56, 16), (10.82, 16), (11.48, 16)])
def test_stab_path_against_sp6_t6(d0, j_live):
    # SP6 t6's live DashStab hits (combo/model_calib_bot.txt): the frame after the dash's mask, 15-16; SP6's model said
    # 14 for the near ones (the Idle body front 2.25 and the dash one frame early)
    assert abs(cs.stab_path(d0)["hit"] - j_live) <= 1


def test_gravity_and_body_front():
    assert cs.GRAV == 60.0 and cs.BODY_FRONT == pytest.approx(1.873)
    # her recoil lands ~17-18 frames after its top (live: control back at g21-22 ~2.3 u up, on the floor at g39-42)
    p = cs.stab_path(11.0)
    assert 15 <= p["land"] - (p["hit"] + cs.HIT_WAIT + cs.REC_F) <= 19


def test_stop_plan():
    c = cs.StabCfg()
    # a tap: the dash's own 3.3 u
    p = cs.stop_plan(7.6, c)
    assert p["tap"] and c.stop_lo <= p["x_stop"] <= c.stop_u + c.tap_room
    # held into the sprint, released inside the grace
    p = cs.stop_plan(9.5, c)
    assert not p["tap"] and cs.DASH_F < p["jr"] <= cs.DASH_F + c.grace_f and p["x_stop"] <= c.stop_u
    assert cs.stop_plan(6.0, c) is None                    # a tap overshoots into its body
    assert cs.stop_plan(13.0, c) is None                   # past the grace
    assert cs.sprint_travel(cs.DASH_F) == pytest.approx(7 * 28 / 60)


def hero(s, clip=None, vx=0.0, feet=0.0, acc=True, atk_cd=0.0):
    h = s["hero"]
    h["anim"] = {"clip": clip or "Idle"}
    h["vel"] = [vx, 0.0]
    h["box"][1] = 3.015 + feet
    h["hero_accepting_input"] = acc
    h["tm"] = {"dash_cd": 0.0, "atk_cd": atk_cd}
    return s


def jump_state(f, k, x0, flip=False):
    """The states after the antic (Jump Aim at 56)."""
    s = antic_state(f, 15, x0, flip=flip)
    st, tin = ("Jump", (k - 56) / 60.0)
    s["ents"][0]["fsms"][0].update({"state": st, "t": tin})
    return s


def run_combo(flip, feet_at_aim=4.5, cfg=None, n=110, latch=None):
    """A toy jump cast: the DashStab hits at antic frame 15, the RS clip from the frame after the press, its hit 9
    frames later (then the bounce), the Jump Aim at 56; the hero does not move."""
    c = cs.CastStab(cfg, dash_slash=True, combo=True, stop=False)
    masks, k_hit, k_rs, k_rs_hit = {}, 15, None, None
    for k in range(0, n):
        f = 1000 + k
        ev, clip, ground = [], "Idle", True
        if k == k_hit:
            ev = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "src": "DashStab"}}]
        if k > k_hit + 1:
            clip, ground = "Wanderer DashRecoil", False
        if k_rs is None and masks.get(k) and masks[k] & sp.M_A and k > k_hit:
            k_rs = k + 1                                     # the RS clip from the frame after the press
        if k_rs is not None and k >= k_rs:
            clip = "Wanderer RecoilStab"
            if k == k_rs + 9:
                k_rs_hit = k
                ev = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "src": "RecoilStab"}}]
            if k >= k_rs + 9:
                clip = "DownSpikeBounce 1"
        s = antic_state(f, k, 10.6, flip=flip, ground=ground, ev=ev) if k < 56 else jump_state(f, k, 10.6, flip)
        m = c.step(f, hero(s, clip, feet=0.0 if ground else feet_at_aim), ground, True, t_game=f / 60.0,
                   latch=latch)
        if m is not None:
            masks[k + 2] = m
    return c, masks, k_hit, k_rs_hit


@pytest.mark.parametrize("flip", [False, True])
def test_the_combo(flip):
    c, masks, k_hit, k_rs_hit = run_combo(flip)
    face = 1 if flip else -1
    toward = sp.M_R if -face > 0 else sp.M_L
    r = c.done[-1]
    assert r.rs and r.k_hit == pytest.approx(k_hit)
    # the dash held with the key toward it until the hit
    assert all(masks[k] & sp.M_DASH and masks[k] & toward for k in range(2, k_hit + 2))
    # no key from the hit to the press; the attack on g16-17 (the mask's game frames); then nothing until the aim + 10
    aim = 56
    after = sorted(k for k in masks if k_hit + 1 < k < aim + c.cfg.post_aim_f)
    a = [k - k_hit for k in after if masks[k] & sp.M_A]
    assert a == [16, 17]
    assert all(masks[k] in (0, sp.M_A) for k in after)
    assert r.rs_start_g is not None and r.rs_hit_g == pytest.approx(k_rs_hit - k_hit)
    # the way under: the key toward it from aim + 10, the air dash at aim + 16 .. 19, then toward (the toy hero does not
    # move: no clear, the end at aim + under_end_f)
    under = sorted(k for k in masks if k >= aim + c.cfg.post_aim_f)
    assert under[0] == aim + c.cfg.post_aim_f
    dash = [k - aim for k in under if masks[k] & sp.M_DASH]
    assert dash == list(range(c.cfg.under_dash_f, c.cfg.under_dash_f + c.cfg.under_dash_hold))
    assert all(masks[k] & toward and not masks[k] & sp.M_A for k in under)
    assert max(under) == aim + c.cfg.under_end_f and r.why == "under end"
    st = c.stats()
    assert st["rs_planned"] == 1 and st["rs_started"] == 1 and st["rs_hit"] == 1 and len(st["runs"]) == 1


def test_combo_no_under():
    # too high at aim + 10 (her top above its body's bottom at the dash), or under off: the planner at aim + 10
    for feet, cfg, why in ((6.0, None, "post (high)"), (4.5, cs.StabCfg(under=0), "post (off)")):
        c, masks, _, _ = run_combo(False, feet_at_aim=feet, cfg=cfg)
        assert c.done[-1].why == why and max(masks) == 56 + c.cfg.post_aim_f - 1


def test_prep_waits_for_the_key_filter():
    # a planner key away from it latched on the frame before: the key toward it first, the dash a frame later
    face = -1                                                # flip False: it faces left, she is on its left
    toward = sp.M_R if -face > 0 else sp.M_L
    away = sp.M_L if toward == sp.M_R else sp.M_R
    sent = {1001: away}
    def latch_for(f):
        def latch(m):
            seq = [sent.get(fr, 0) for fr in range(f - 1, f + 2)] + [m]
            lat, _ = kin.hold_filter(np.array(seq), kin.HoldState.idle(1))
            return int(lat[-1])
        return latch
    c = cs.CastStab(dash_slash=True, combo=True, stop=False)
    out = {}
    for k in range(0, 6):
        f = 1000 + k
        m = c.step(f, hero(antic_state(f, k, 10.6)), True, True, t_game=f / 60.0, latch=latch_for(f))
        if m is not None:
            sent[f + 2] = out[f + 2] = m
    assert out[1002] == toward and out[1003] == toward | sp.M_DASH
    assert c.run.phase == "lunge" and c.run.j0 == 1003 and c.run.prep == 1


def test_combo_gates():
    # below combo_d_min: the SP6 stab only (its landing rule)
    c = cs.CastStab(dash_slash=True, combo=True, stop=False)
    assert c.step(1000, hero(antic_state(1000, 2, 9.85)), True, t_game=1000 / 60) is not None
    assert not c.run.rs
    # the RS hit predicted by rs_k_max: at antic frame 12 from 10.6 u (hit j15, RS 12 + 15 + 25 = 52) yes; from 11.9 u
    # (hit j18) no, and the stab alone lands late
    c = cs.CastStab(dash_slash=True, combo=True, stop=False)
    assert c.step(1000, hero(antic_state(1000, 10, 10.6)), True, t_game=1000 / 60) is not None
    assert c.run.rs
    c = cs.CastStab(dash_slash=True, combo=True, stop=False)
    assert c.step(1000, hero(antic_state(1000, 10, 11.9)), True, t_game=1000 / 60) is None
    assert c.stats().get("no_lands late") == 1
    c = cs.CastStab(dash_slash=True, combo=True, stop=False)
    assert c.step(1000, hero(antic_state(1000, 6, 11.9)), True, t_game=1000 / 60) is not None
    assert c.run.rs
    # without COMBO never
    c = cs.CastStab(dash_slash=True, combo=False, stop=False)
    c.step(1000, hero(antic_state(1000, 2, 10.6)), True, t_game=1000 / 60)
    assert not c.run.rs


def test_combo_no_rs_clip_hands_back():
    c = cs.CastStab(dash_slash=True, combo=True, stop=False)
    out = {}
    for k in range(0, 60):
        f = 1000 + k
        ev = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "src": "DashStab"}}] if k == 15 else []
        s = hero(antic_state(f, k, 10.6, ground=k <= 16, ev=ev), "Idle" if k <= 16 else "Wanderer DashRecoil")
        out[k] = c.step(f, s, k <= 16, True, t_game=f / 60.0)
    assert c.done[-1].why == "no rs" and out[59] is None


@pytest.mark.parametrize("flip", [False, True])
@pytest.mark.parametrize("x0", [7.6, 9.6])
def test_the_stop(flip, x0):
    """A toy run: she moves 28 u/s in the dash, then the sprint, stops dead on the release (moving through its frame);
    each landed slash knocks it 0.48 u away from her."""
    c = cs.CastStab(dash_slash=False, combo=False, stop=True)
    face = 1 if flip else -1
    toward = sp.M_R if -face > 0 else sp.M_L
    cx = 31.0
    hx = cx + face * x0
    keys = {}
    j0 = rel = None
    hits = 0
    for k in range(0, 56):
        f = 1000 + k
        m_now = keys.get(k, 0)                               # the mask on this frame
        j = None if j0 is None else k - j0
        moving = rel is None and j is not None and j >= 1
        v = 0.0
        if moving:
            v = cs.DASH_V if j <= cs.DASH_F else max(cs.SPRINT_V, cs.DASH_V - cs.SPRINT_DEC * (j - cs.DASH_F))
            hx -= face * v / 60.0
            if not m_now & sp.M_DASH and j >= cs.DASH_F:
                rel = k
        elif rel is not None and m_now & toward:
            hx -= face * sp.WALK_U
        clip = "Dash" if moving and j <= cs.DASH_F else "Sprint" if moving else "Idle"
        ev = []
        if m_now & sp.M_A and not keys.get(k - 1, 0) & sp.M_A and (hx - cx) * face <= 4.89:
            ev = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "src": "Slash"}}]
            hits += 1
            cx -= face * 0.48                                # knocked back, away from her
        s = antic_state(f, k, (hx - cx) * face, cx=cx, flip=flip, ev=ev)
        hero(s, clip, vx=-face * v)
        m = c.step(f, s, True, True, t_game=f / 60.0)
        if m is not None:
            keys[k + 2] = m
            j0 = k + 2 if j0 is None else j0
    r = (c.done + [c.run])[0]
    assert r.mode == "stop" and r.rel_j is not None
    assert 3.4 <= r.x_stop <= 4.9
    p = sorted(r.presses)
    assert len(p) >= 2 and all(b - a >= c.cfg.slash_cd for a, b in zip(p, p[1:]))
    assert hits >= 2
    first, second = round(p[0]), round(p[1])
    assert keys[first] == sp.M_A                              # the first press: no direction key
    assert keys[second] & sp.M_A and keys[second] & toward and keys[second - 1] & toward
    assert not any(m & sp.M_DASH for kk, m in keys.items() if kk >= j0 + r.rel_j)


def test_stop_no_start():
    c = cs.CastStab(dash_slash=False, combo=False, stop=True)
    assert c.step(1000, hero(antic_state(1000, 2, 6.0)), True, t_game=1000 / 60) is None
    assert c.step(1100, hero(antic_state(1100, 2, 13.0)), True, t_game=1100 / 60) is None
    assert c.stats().get("no_distance") == 2


def test_both_on_split_by_distance():
    c = cs.CastStab(dash_slash=True, combo=True, stop=True)
    c.step(1000, hero(antic_state(1000, 2, 10.6)), True, t_game=1000 / 60)
    assert c.run.mode == "stab" and c.run.rs
    c = cs.CastStab(dash_slash=True, combo=True, stop=True)
    c.step(1000, hero(antic_state(1000, 2, 7.6)), True, t_game=1000 / 60)
    assert c.run.mode == "stop"


def test_both_on_prefers_the_stop_to_a_lone_stab():
    # 9.85 u: the stab would go without the RS (below combo_d_min) - the stop's two slashes instead
    c = cs.CastStab(dash_slash=True, combo=True, stop=True)
    c.step(1000, hero(antic_state(1000, 2, 9.85)), True, t_game=1000 / 60)
    assert c.run.mode == "stop"
    # 12 u: past the stop's grace - the stab with the RS
    c = cs.CastStab(dash_slash=True, combo=True, stop=True)
    c.step(1000, hero(antic_state(1000, 2, 12.0)), True, t_game=1000 / 60)
    assert c.run.mode == "stab" and c.run.rs


def test_the_dash_frame_distance():
    # running toward it at 8.25 u/s: the start reads her x on the dash's frame (2 frames on: 0.275 u nearer)
    c = cs.CastStab(dash_slash=True, combo=True, stop=False)
    s = hero(antic_state(1000, 2, 10.1), vx=8.25)          # flip False: it faces left, she is on its left: +x toward
    c.step(1000, s, True, t_game=1000 / 60)
    assert c.run.pred["x_dash"] == pytest.approx(10.1 - 0.275, abs=0.01) and not c.run.rs
    # SP8 t2 ep 0: 9.52 u at the STATE, running in - 9.19 at the dash: the stab's lunge on after the hit reaches its body
    c = cs.CastStab(dash_slash=True, combo=False, stop=False)
    assert c.step(1000, hero(antic_state(1000, 2, 9.52), vx=8.25), True, t_game=1000 / 60) is None
    assert c.stats().get("no_too close") == 1


def test_no_rs_blocks_the_attack_to_g31():
    # a stab without the RS planned: no key until g31 even after her control is back (an attack would make an RS)
    c = cs.CastStab(dash_slash=True, combo=False, stop=False)
    out = {}
    for k in range(0, 60):
        f = 1000 + k
        ev = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "src": "DashStab"}}] if k == 15 else []
        clip = "Idle" if k <= 16 else "Wanderer DashRecoil" if k < 37 else "Airborne"
        out[k] = c.step(f, hero(antic_state(f, k, 10.4, ground=k <= 16, ev=ev), clip), k <= 16, True, t_game=f / 60)
    assert all(out[k] == 0 for k in range(16, 15 + c.cfg.rs_block_g)) and out[15 + c.cfg.rs_block_g] is None
    assert c.done[-1].why == "control"


def test_rs_only_from_far_enough():
    # the recoil leaves her 6.0 u out (< rs_x_min 6.75): no RS press, no key to g31, then the planner
    c = cs.CastStab(dash_slash=True, combo=True, stop=False)
    out = {}
    for k in range(0, 60):
        f = 1000 + k
        ev = [{"k": "hit", "d": {"type_key": sp.CLAPPER, "src": "DashStab"}}] if k == 15 else []
        x = 10.6 if k <= 15 else 6.0
        clip = "Idle" if k <= 16 else "Wanderer DashRecoil" if k < 37 else "Airborne"
        out[k] = c.step(f, hero(antic_state(f, k, x, ground=k <= 16, ev=ev), clip), k <= 16, True, t_game=f / 60)
    assert not any(m and m & sp.M_A for k, m in out.items() if k > 15)
    r = c.done[-1]
    assert not r.rs and r.why == "rs near" and r.rs_x == pytest.approx(6.0)
    assert all(out[k] == 0 for k in range(16, 15 + c.cfg.rs_block_g)) and out[15 + c.cfg.rs_block_g] is None


def test_no_start_through_a_rune_circle():
    c = cs.CastStab(dash_slash=True, combo=True, stop=True)
    s = hero(antic_state(1000, 2, 10.6))
    hx = sp.hero_x(s)
    rune = {"type_key": "damager", "pos": [hx + 3.0, 3.34], "colliders": [
        {"name": "c", "enabled": False, "verts_world": [hx + 3.0 - cs.RUNE_R, 3.0, hx + 3.0 + cs.RUNE_R, 3.0,
                                                         hx + 3.0, 10.5]}]}
    s["ents"].append(rune)
    assert c.step(1000, s, True, t_game=1000 / 60) is None and c.run is None
    s2 = hero(antic_state(1001, 3, 10.6))                     # gone: the start goes
    assert c.step(1001, s2, True, t_game=1001 / 60) is not None


def test_one_clapper_only():
    # two live Clappers: no start (the person's two-Clapper rules differ; SP9)
    c = cs.CastStab(dash_slash=True, combo=True, stop=True)
    s = hero(antic_state(1000, 2, 10.6))
    other = dict(s["ents"][0], iid=8, pos=[45.0, 7.45])
    other["fsms"] = [{"name": "Control", "state": "Idle", "t": 0.3}]
    s["ents"].append(other)
    assert c.step(1000, s, True, t_game=1000 / 60) is None and c.stats().get("no_two") == 1
