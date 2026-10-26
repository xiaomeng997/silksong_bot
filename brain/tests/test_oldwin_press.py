"""Task oldwin stage N: the slam windows by the reflex's path (ssbot.map2.oldwin_press) - off by default, the reflex's
new options default to the old behaviour, the Press's phase confirmations end it when the game does not follow."""
import types

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import oldwin_press as op
from ssbot.map2 import reflex as rx


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_WINDOWS_PRESS", raising=False)
    assert not op.enabled()
    from ssbot.train import forum_planner_policy as fpp
    assert fpp.ForumPlannerPolicy.wpress is None          # a class default: no instance attribute when off


def test_reflex_new_options_default_to_the_old():
    R = rx.Reflex(rx.Table(), W=None)
    assert R.types is None and R.cl_ready is False
    import inspect
    assert inspect.signature(R.check).parameters["bridge"].default == 0
    assert inspect.signature(rx._closed_ds).parameters["k_lo"].default is None
    assert inspect.signature(rx._closed_cl).parameters["k_lo"].default is None


def test_cl_ready_rejects_an_attack_under_way():
    from ssbot.map2 import search as ms
    W = ms.World()
    S = km.initial_state(W.params, 30.0, 3.015 + W.params.foot, ground=True, facing=1)
    S = np.asarray(S, float).reshape(km.K, -1)[:, 0]
    raw = rx.render(rx.Macro("cl", hop=0, wait=0, k=None), 1)
    assert rx._cl_ready(W, S, raw)
    S2 = S.copy()
    S2[km.ATTACKING] = 0.2
    assert not rx._cl_ready(W, S2, raw)


class _Win:
    def __init__(self, obs):
        self._obs = obs
        self.gk = 0
        self.trk = types.SimpleNamespace(mems=lambda: {}, hazards=lambda K: [])

    def obs(self):
        return self._obs


def _raw(f, clip="Idle", mask=0, acc=True, x=30.0, ev=()):
    return {"f": f, "hero": {"anim": {"clip": clip}, "hero_accepting_input": acc, "pos": [x, 4.5]},
            "act": {"mask": mask}, "dt": 1.0 / 60.0, "ev": list(ev)}


def _wp(obs):
    wp = op.WinPress(_Win(obs), inproc=True)
    return wp


def _o(iid=7, st="Slam Antic", j=10, x=35.0):
    return cm.Obs(iid, st, j / 60.0, x, 4.2, 0.0, 0.0, -1, 230, st, j=j)


def _run(wp, frames, clips, masks=None, ev=None):
    out = {}
    S0 = np.zeros(km.K)
    S0[km.PX] = 30.0
    for f in frames:
        r = _raw(f, clips.get(f, "Idle"), (masks or {}).get(f, 0), acc=not clips.get(f, "Idle").startswith("Harpoon"),
                 ev=(ev or {}).get(f, ()))
        wp.feed(r, f)
        out[f] = wp._decide(f, f, r, S0, np.zeros(1, np.int64), None, None, {}, False, False)
    return out


def test_clawline_never_hooked_ends_the_press():
    """CLAWSTRIKE's live failure (stage L H1): a Clawline eaten (no Harpoon clip) must not be taken as control."""
    wp = _wp([_o()])
    P = 101
    cmds = np.array([0, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT], np.int64)
    alts = {"early": (P + 26, -2.0, np.zeros(40, np.int64), P + 36, 0)}
    wp.press = rx.Press("claw_slam0", 7, None, rx.Macro("cl"), (1, 1), 100, cmds, 160, (140, 142), alts, P + 1, 4.0,
                        0.0, d=1, p_abs=P, strike="down")
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None}
    _run(wp, range(99, 106), {}, masks={101: rx.M_CLAW, 102: rx.M_CLAW, 103: rx.M_CLAW})
    assert wp.press is None
    assert any(x.get("why") == "no hook" for x in wp.log)


def test_clawline_missed_needle_ends_the_press():
    wp = _wp([_o()])
    P = 101
    cmds = np.array([0, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT], np.int64)
    alts = {"early": (P + 26, -2.0, np.zeros(40, np.int64), P + 36, 0)}
    wp.press = rx.Press("claw_slam0", 7, None, rx.Macro("cl"), (1, 1), 100, cmds, 160, (140, 142), alts, P + 1, 4.0,
                        0.0, d=1, p_abs=P, strike="down")
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None}
    clips = {f: "Harpoon Antic" for f in range(102, 110)}
    clips.update({f: "Harpoon Throw" for f in range(110, 118)})
    _run(wp, range(99, 122), clips, masks={101: rx.M_CLAW, 102: rx.M_CLAW, 103: rx.M_CLAW})
    assert wp.press is None
    assert any(x.get("why") == "hook missed" for x in wp.log)


def test_down_slash_without_a_swing_ends_the_press():
    wp = _wp([_o()])
    cmds = np.zeros(30, np.int64)
    cmds[8:10] = km.B_ATTACK | km.B_DOWN
    wp.press = rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 100, cmds, 129, (112, 114), {}, 0, 10.0,
                        0.0, d=1, t_abs=108, strike="down")
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None}
    _run(wp, range(99, 112), {})
    assert wp.press is None
    assert any(x.get("why") == "no swing" for x in wp.log)


def test_down_slash_contact_plays_to_the_end():
    wp = _wp([_o()])
    cmds = np.zeros(30, np.int64)
    cmds[8:10] = km.B_ATTACK | km.B_DOWN
    wp.press = rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 100, cmds, 129, (112, 114), {}, 0, 10.0,
                        0.0, d=1, t_abs=108, strike="down")
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None}
    clips = {f: "DownSlashAlt" for f in range(108, 116)}
    ev = {111: [{"k": "hit", "d": {"ent": 7, "src": "DownSlash"}}]}
    out = _run(wp, range(99, 125), clips, ev=ev)
    assert wp.press is not None and wp.pinfo["contact"] == 111
    assert out[106] == int(cmds[8])                         # the key for f + 2 = 108


def test_commit_needs_the_bridge_keys_sent():
    wp = _wp([_o(j=10)])
    p = rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 105, np.zeros(20, np.int64), 124, (117, 119), {},
                 0, 10.0, 0.0, d=1, t_abs=113, strike="down")
    snap = {"seq": 1, "f": 100, "fo": 100, "g": 0, "bridge": np.array([km.B_RIGHT, km.B_RIGHT, 0], np.int64),
            "obs": [_o(j=10)], "kind": "check"}
    wp.out = snap
    pred = np.tile(np.array([[30.0, 4.5]]), (8, 1))
    wp.pend = [(102, {"kind": "now", "seq": 1, "press": p, "pred": pred, "lane": None, "ms": 5.0})]
    S0 = np.zeros(km.K)
    S0[km.PX], S0[km.PY] = 30.0, 4.5
    sent = {102: km.B_LEFT, 103: km.B_RIGHT}                # the key sent for 102 is not the bridge's
    wp._decide(102, 102, _raw(102), S0, np.zeros(1, np.int64), None, None, sent, False, False)
    assert wp.commit is None and wp.st["commit_keys"] == 1


# ---- stage F2: the reviewers' safety findings ------------------------------------------------------------------------

def _claw_press(P=101):
    cmds = np.array([0, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT], np.int64)
    post = np.zeros(60, np.int64)
    post[30:33] = km.B_ATTACK | km.B_DOWN
    alts = {"early": (P + 26, 0.0, post, P + 34, 0)}
    return rx.Press("claw_slam0", 7, None, rx.Macro("cl"), (1, 1), 100, cmds, 170, (140, 142), alts, P + 1, 4.0,
                    0.0, d=1, p_abs=P, strike="down")


def _ds_press():
    cmds = np.zeros(30, np.int64)
    cmds[8:10] = km.B_ATTACK | km.B_DOWN
    return rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 100, cmds, 129, (112, 114), {}, 0, 10.0, 0.0,
                    d=1, t_abs=108, strike="down")


def _env(iids=(7,), st="Slam Antic", j0=10, x=35.0, n=80):
    """A one-outcome world envelope: the Clappers in `st` from frame j0 at the snapshot's game frame."""
    k = np.arange(n, dtype=float)
    rec = (k, k, np.ones(n, np.int16), j0 + k, np.full(n, x), np.full(n, -1.0))
    return {"iids": list(iids), "names": {st: 1}, "T": n, "br": [{int(i): rec for i in iids}]}


def _f2(wp, press, sfo=97, env=None):
    wp.f2 = True
    wp.press = press
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None,
                "sfo": sfo, "sg": 0, "env": env, "latched": None}
    return wp


def _run2(wp, frames, clips=None, masks=None, ev=None, obs_at=None, dt_at=None, crit_at=(), g0=97):
    """As _run with the tracker's game clock (gk = f - g0), the observed Clappers per frame, freezes, crit ticks."""
    out = {}
    S0 = np.zeros(km.K)
    S0[km.PX] = 30.0
    clips = clips or {}
    for f in frames:
        if obs_at and f in obs_at:
            wp.win._obs = obs_at[f]
        wp.win.gk = f - g0
        c = clips.get(f, "Idle")
        r = _raw(f, c, (masks or {}).get(f, 0), acc=not c.startswith("Harpoon"), ev=(ev or {}).get(f, ()))
        if dt_at and f in dt_at:
            r["dt"] = dt_at[f]
        wp.feed(r, f)
        out[f] = wp._decide(f, f, r, S0, np.zeros(1, np.int64), None, None, {}, False, f in crit_at)
    return out


def _ends(wp):
    return [(x["f"], x["why"]) for x in wp.log if x.get("ev") == "end"]


def _track(f0=99, f1=112):
    return {f: [_o(j=10 + f - 97)] for f in range(f0, f1)}


def test_f2_her_damage_ends_the_press():
    wp = _f2(_wp([_o(j=12)]), _ds_press(), env=_env(j0=10))
    ev = {103: [{"k": "damage", "d": {"source": "Slam Collider 1", "amount": 2}}]}
    _run2(wp, range(99, 112), ev=ev, obs_at=_track())
    assert wp.press is None and _ends(wp)[0] == (103, "hurt")


def test_f2_the_target_off_the_checked_world_ends_the_press():
    wp = _f2(_wp([_o(j=12)]), _ds_press(), env=_env(j0=10))
    obs_at = _track()
    obs_at[104] = [_o(st="Stun", j=0)]
    _run2(wp, range(99, 112), obs_at=obs_at)
    assert wp.press is None and _ends(wp)[0] == (104, "world")


def test_f2_another_clapper_the_check_never_saw_ends_the_press():
    wp = _f2(_wp([_o(j=12)]), _ds_press(), env=_env(j0=10))
    obs_at = _track()
    for f in range(102, 112):
        obs_at[f] = obs_at[f] + [_o(iid=8, st="Slam 1", j=2, x=30.5)]
    _run2(wp, range(99, 112), obs_at=obs_at)
    assert _ends(wp)[0] == (102, "world")


def test_f2_the_world_as_checked_plays_on():
    wp = _f2(_wp([_o(j=12)]), _ds_press(), env=_env(j0=10))
    out = _run2(wp, range(99, 107), obs_at=_track())
    assert wp.press is not None and not _ends(wp) and out[106] == int(km.B_ATTACK | km.B_DOWN)


def test_f2_a_freeze_after_the_snapshot_ends_the_press():
    """Stage N looked from f0 - 1 = 99 on: a freeze at 98 (the bridge's last frames) went unseen."""
    wp = _f2(_wp([_o()]), _ds_press(), sfo=97)
    _run2(wp, range(98, 104), dt_at={98: 0.0})
    assert _ends(wp) and _ends(wp)[0] == (98, "freeze")
    wp2 = _f2(_wp([_o()]), _ds_press(), sfo=97)
    wp2.f2 = False                                          # stage N's rule
    _run2(wp2, range(98, 104), dt_at={98: 0.0})
    assert not _ends(wp2) and wp2.press is not None


def test_f2_a_clawline_latched_a_frame_late_keeps_the_press_shifted():
    """map2 L1's B2 (the review's finding 1): latched at 102 for P 101, the hook fires - the Press follows it."""
    wp = _f2(_wp([_o(x=30.0)]), _claw_press(101))
    clips = {f: "Harpoon Antic" for f in range(103, 111)}
    clips.update({f: "Harpoon Dash" for f in range(111, 128)})
    _run2(wp, range(99, 132), clips=clips, masks={102: rx.M_CLAW, 103: rx.M_CLAW, 104: rx.M_CLAW})
    assert not any(w == "claw not latched" for _, w in _ends(wp))
    assert wp.st["claw_late"] == 1
    assert wp.press is not None and wp.press.p_abs == 102 and wp.press.alts["early"][3] == 101 + 34 + 1
    assert wp.pinfo["ctrl"] == 128


def test_f2_a_clawline_never_latched_ends_after_its_key_frames():
    wp = _f2(_wp([_o()]), _claw_press(101))
    _run2(wp, range(99, 106))
    assert _ends(wp) == [(103, "claw not latched")]


def test_f2_no_world_end_once_the_clawline_key_is_out():
    """A world mismatch with the Clawline's key sent must not hand a hook in flight to the planner."""
    wp = _f2(_wp([_o(j=12)]), _claw_press(101), env=_env(j0=10))
    obs_at = {f: [_o(st="Slam 1", j=1)] for f in range(100, 112)}
    clips = {f: "Harpoon Antic" for f in range(102, 111)}
    _run2(wp, range(100, 106), clips=clips, masks={101: rx.M_CLAW, 102: rx.M_CLAW, 103: rx.M_CLAW}, obs_at=obs_at)
    assert wp.press is not None and not _ends(wp)


def test_f2_a_critical_script_window_ends_a_down_slash_press_not_a_hook():
    wp = _f2(_wp([_o()]), _ds_press())
    _run2(wp, range(99, 104), crit_at={101})
    assert _ends(wp) == [(101, "crit")]
    wp2 = _f2(_wp([_o()]), _claw_press(101))
    _run2(wp2, range(100, 104), masks={101: rx.M_CLAW, 102: rx.M_CLAW, 103: rx.M_CLAW}, crit_at={101})
    assert not _ends(wp2) and wp2.press is not None


def test_f2_commit_refuses_other_latched_keys_and_attack_state():
    def setup():
        wp = _wp([_o(j=10)])
        wp.f2 = True
        p = rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 105, np.zeros(20, np.int64), 124, (117, 119),
                     {}, 0, 10.0, 0.0, d=1, t_abs=113, strike="down")
        wp.out = {"seq": 1, "f": 100, "fo": 100, "g": 0, "bridge": np.array([km.B_RIGHT, km.B_RIGHT, 0], np.int64),
                  "obs": [_o(j=10)], "kind": "check"}
        pred = np.tile(np.array([[30.0, 4.5]]), (8, 1))
        v = {"kind": "now", "seq": 1, "press": p, "pred": pred, "lane": None, "ms": 5.0,
             "pred_lat": np.array([km.B_RIGHT, km.B_RIGHT, km.B_RIGHT, 0], np.int64), "pred_atk": np.zeros((5, 2))}
        wp.pend = [(101, v)]
        return wp
    S0 = np.zeros(km.K)
    S0[km.PX], S0[km.PY] = 30.0, 4.5
    sent = {102: km.B_RIGHT}
    wp = setup()
    wp.feed(_raw(101, mask=km.B_LEFT), 101)              # latched B_LEFT where the model had B_RIGHT
    wp._decide(101, 101, _raw(101), S0, np.zeros(1, np.int64), None, None, sent, False, False)
    assert wp.commit is None and wp.st["commit_lat"] == 1
    wp = setup()
    wp.feed(_raw(101, mask=km.B_RIGHT), 101)
    S1 = S0.copy()
    S1[km.ATTACKING] = 0.2                                 # an attack under way the model did not have
    wp._decide(101, 101, _raw(101), S1, np.zeros(1, np.int64), None, None, sent, False, False)
    assert wp.commit is None and wp.st["commit_atk"] == 1
    wp = setup()
    wp.feed(_raw(101, mask=km.B_RIGHT), 101)
    wp._decide(101, 101, _raw(101), S0, np.zeros(1, np.int64), None, None, sent, False, False)
    assert wp.commit is not None


def test_f2_positions_held_against_her_rendered_position():
    """The check's 'pred' / 'lane' are the rollout's rendered positions (hero.pos); stage N held them against her kin
    state's PX / PY (not the rendered position: 17 % of recorded frames > 0.15 u apart) - F2 against hero.pos."""
    wp = _wp([_o(j=10)])
    wp.f2 = True
    p = rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 105, np.zeros(20, np.int64), 124, (117, 119),
                 {}, 0, 10.0, 0.0, d=1, t_abs=113, strike="down")
    wp.out = {"seq": 1, "f": 100, "fo": 100, "g": 0, "bridge": np.array([km.B_RIGHT, km.B_RIGHT, 0], np.int64),
              "obs": [_o(j=10)], "kind": "check"}
    pred = np.tile(np.array([[30.0, 4.5]]), (8, 1))
    wp.pend = [(101, {"kind": "now", "seq": 1, "press": p, "pred": pred, "lane": None, "ms": 5.0})]
    S0 = np.zeros(km.K)
    S0[km.PX], S0[km.PY] = 30.3, 4.2                     # the kin state off the rendered path by 0.3 u
    wp.feed(_raw(101, mask=km.B_RIGHT, x=30.0), 101)      # (_raw: hero.pos (x, 4.5))
    wp._decide(101, 101, _raw(101), S0, np.zeros(1, np.int64), None, None, {102: km.B_RIGHT}, False, False)
    assert wp.commit is not None and wp.st["commit_pos"] == 0


def test_f2_the_bridge_with_two_clappers():
    """SSBOT_FORUM_WINDOWS_PRESS_L2: the snapshot's bridge L2 frames long while two Clappers live (finding 11)."""
    sent = []
    for obs, want in (([_o(j=10)], 3), ([_o(j=10), _o(iid=8, j=10, x=40.0)], 5)):
        wp = _wp(obs)
        wp.L2 = 5
        wp._send = lambda sn, out, _s=sent: _s.append(sn)
        S0 = np.zeros(km.K)
        S0[km.PX] = 30.0
        wp._post(100, 99, _raw(99), S0, np.zeros(2, np.int64), None, 0, "plan", np.zeros(12, np.int64), False)
        assert sent and sent[-1]["L"] == want and len(sent[-1]["inflight"]) == 2 + want


def test_f2_swing_fix_sets_the_down_slash_flags():
    S = np.zeros(km.K)
    S[km.ATTACKING], S[km.ATK_PDIR], S[km.ATK_KIND] = 0.2, 0.0, 1.0
    S2 = op.swing_fix(S, {"hero": {"anim": {"clip": "DownSlashAlt"}}})
    assert S2[km.ATK_PDIR] == 2.0 and S2[km.ATK_KIND] == 0.0 and S[km.ATK_PDIR] == 0.0
    S3 = op.swing_fix(S, {"hero": {"anim": {"clip": "Slash"}}})
    assert S3[km.ATK_PDIR] == 0.0


def test_f2_envelope_and_world_ok(monkeypatch):
    from ssbot.map2 import brnum
    monkeypatch.setattr(brnum, "ON", [False])
    # one branch: Slam Antic j 10 + k to k 19, then Slam 0 drawn with a timing spread of 0 .. 2 frames (the slam's
    # 48 / 49-frame antic and more: the game is anywhere in it)
    recs = {7: [(k, 0, 0 if k < 20 else 2, "Slam Antic" if k < 20 else "Slam 0", 10 + k if k < 20 else k - 20, 35.0,
                 4.2, -1, 0) for k in range(0, 40)]}
    b = types.SimpleNamespace(recs=recs)
    env = op.envelope([(types.SimpleNamespace(branches=[b], T=60), 4)], [7])
    assert env["T"] == 60 and len(env["br"]) == 1
    assert op.world_ok(env, 3, [_o(j=13)]) and not op.world_ok(env, 3, [_o(j=16)])
    assert op.world_ok(env, 22, [_o(st="Slam 0", j=2)]) and not op.world_ok(env, 22, [_o(j=32)])
    assert op.world_ok(env, 23, [_o(st="Slam 0", j=1)])                      # a frame late: inside the spread
    assert not op.world_ok(env, 3, [_o(j=13), _o(iid=8, j=13)])              # a Clapper the check never saw
    assert op.world_ok(env, 3, [_o(j=13, x=35.5)], frozenset({7})) and not op.world_ok(env, 3, [_o(j=13, x=35.5)])
    assert not op.world_ok(env, 3, [cm.Obs(7, "Slam Antic", 13 / 60.0, 35.0, 4.2, 0.0, 0.0, 1, 230, "x", j=13)])
    assert op.world_ok(env, 61, [_o(st="Stun", j=0)])                        # past the prediction's horizon


def test_f2_switches_default_to_the_old(monkeypatch):
    from ssbot.combat.tactics import gauntlet
    from ssbot.train import forum_planner_policy as fpp
    monkeypatch.delenv("SSBOT_FORUM_WINDOWS_ROWS", raising=False)
    assert fpp._win_rows_on()
    if not any(k in __import__("os").environ for k in ("SSBOT_FORUM_SLAM_PLAY_PREFS", "SSBOT_FORUM_WINDOWS_PRESS_OWN")):
        assert gauntlet.SP4_PREFS is False
        assert op.OWN == ("plan",)
